#Flask imports
from flask import Flask, request, jsonify
import requests

#Parser imports
import feedparser as fp
from newspaper import Article
from bs4 import BeautifulSoup
from dateutil import parser
from dateutil.parser import parse
import re
import readtime
import hashlib

#AWS imports
import boto3
from boto3.dynamodb.conditions import Key
from zappa.asynchronous import task
from botocore.exceptions import ClientError

#default imports
import random
import time
from time import time, mktime, sleep
from math import ceil
import string
import json

app = Flask(__name__)

header_wsj = {
    'Host':'www.wsj.com',
    'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.67 Safari/537.36',
    'Accept':'*/*',
    'Accept-Language':'en-US,en;q=0.9',
    'Accept-Encoding':'gzip, deflate, br',
    'Referer':'https://www.google.com',
    'DNT':'1',
    'Connection':'keep-alive',
    'TE':'Trailers'
}

header_default = {
    'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.67 Safari/537.36'
}

cleaner_list = [
## list of phrases to be removed before summarization
]

dxbmo_imglist = [
## regex for media office links
]

s3 = boto3.resource('s3')
dynamodb = boto3.resource('dynamodb', region_name = 'ap-south-1')
table = dynamodb.Table('news')

serverToken = "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
deviceToken = "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"

@task
def jsonparser(value):
    newsPaper = []
    newsdict = requests.get(value['rss']).json()
    for news in newsdict:
        pub_date = parse(news["publication_date"])
        timestamp = int(mktime(pub_date.timetuple()))
        if time() - timestamp <= 3600:
            article = {}
            # Article timestamp
            article['timestamp'] = str(timestamp)
            # Article URL
            article['url'] = news['uri'].split('?', 1)[0]
            # Article titles
            article['title'] = news['headline']
            # SHA-1 id
            article['id'] = hashlib.md5((article['url'] + article['title']).encode('utf-8')).hexdigest()
            # Article image
            img_src = news["images"][0]["url"]
            article['img'] = img_src.split('?', 1)[0]
            # Article sources
            article['src'] = value['source_en']
            # article['src_a'] = value['source_ar']
            # Article text and summaries
            article['txt'] = news['readOutText']
            for phrase in cleaner_list:
                article['txt'] = article['txt'].replace(phrase, '')

            final_summary = ' '.join(re.split(r'(?<=[.])\s', article['txt'])[:3])
            wordcount = sum([i.strip(string.punctuation).isalpha() for i in final_summary.split()])
            if wordcount >= 70:
                final_summary = ' '.join(re.split(r'(?<=[.])\s', article['txt'])[:2])
            elif wordcount <= 50:
                final_summary = ' '.join(re.split(r'(?<=[.])\s', article['txt'])[:4])
            wordcount = sum([i.strip(string.punctuation).isalpha() for i in final_summary.split()])
            if wordcount >=70: 
                final_summary = ' '.join(re.split(r'(?<=[.])\s', article['txt'])[:1])
            
            article['summary'] = final_summary
            # Article read-time
            article['readtime'] = str(ceil(readtime.of_text(article['txt']).seconds/60))
            # Article category
            article['category'] = value['category']
            article['language'] = value['language']
            article['isSeen'] = 'n'
            if article != {}:
                try:
                    table.put_item(Item = article, ConditionExpression='attribute_not_exists(id)')
                    newsPaper.append(article)
                except ClientError as e:
                    print("--Not added, already present", e)
    return newsPaper

@task
def rssparser(value):
    excludeTexts = value['exclude']
    newsPaper = []
    d = fp.parse(value['rss'])
    for entry in d.entries:
        article = {}
        timestamp = 0
        if hasattr(entry, 'published'):
            pub_date = parse(entry.published)
            timestamp = int(mktime(pub_date.timetuple()))
        elif hasattr(entry, 'updated'):
            pub_date = parse(entry.updated)
            timestamp = int(mktime(pub_date.timetuple()))
        else:
            news3k = Article(entry.link)
            news3k.download()
            news3k.parse()
            if news3k.publish_date is None:
                print("No date entry")
                timestamp = int(time())
            else:
                timestamp = int(mktime(news3k.publish_date.timetuple()))
        # Parsing news link
        if (time() - timestamp <= 3600):
            try:
                final_article = ""
                if "bloomberg.com" in entry.link:
                    sleep(random.uniform(0,2))
                    page = requests.get(entry.link, headers = header_bloomberg)
                elif "wsj.com" in entry.link:
                    sleep(random.uniform(0,2))
                    page = requests.get(entry.link, headers = header_wsj)
                else:
                    sleep(random.uniform(0,1))
                    page = requests.get(entry.link, headers = header_default)
                
                img_src = ""
                soup = BeautifulSoup(page.text, 'html.parser')
                if "mediaoffice.ae" in entry.link:
                    for imgdata in soup.findAll("img", {"class": "img-fluid"}):
                        if imgdata["src"] not in dxbmo_imglist:
                            img_src = "https://www.mediaoffice.ae" + imgdata['src']
                else:
                    img_src = soup.find("meta", property = "og:image", content = True)["content"]
                if img_src is None:
                    img_src = ''
                
                texts = soup.find_all('p')
                list_paragraphs = []

                #Check each sentence
                for p in range(0, len(texts)):
                    paragraph = texts[p].get_text()
                    if len(paragraph) >= 75:
                        #truncate abbreviations
                        paragraph = paragraph.replace('H.H.', 'HH')
                        paragraph = paragraph.replace('H.E.', 'HE')
                        paragraph = paragraph.replace('Brig.', 'Brig')
                        paragraph = paragraph.replace('Lt.', 'Lt')
                        paragraph = paragraph.replace('Maj.', 'Maj')
                        paragraph = paragraph.replace('Eng.', 'Eng')
                        paragraph = paragraph.replace('Mr. ', '')
                        paragraph = paragraph.replace('Ms. ', '')
                        paragraph = paragraph.replace('Dr. ', '')
                        paragraph = paragraph.replace('U.K.', 'UK')
                        paragraph = paragraph.replace('U.S.A.', 'USA')
                        paragraph = paragraph.replace('U.S', 'US')
                        paragraph = paragraph.replace('Inc.', 'Inc')
                        paragraph = paragraph.replace('Govt.', 'Govt')
                        paragraph = paragraph.replace('govt.', 'govt')
                        re.sub(' +', ' ', paragraph)

                        #exclude sentences containing the excluded phrases
                        if paragraph not in excludeTexts
                        and not((p == 0 or p == 1 or p == 2)  and "By" in paragraph):
                            list_paragraphs.append(paragraph)
                            list_paragraphs = [x for x in list_paragraphs if x!= '']
                            list_paragraphs = [x for x in list_paragraphs if x!= ' ']
                
                start = 0
                end = len(list_paragraphs)
                # site-specific regexes
                if 'start' in value:
                    start = int(value['start'])
                    if "hindu.com" in entry.link and img_src == "https://www.thehindu.com/static/theme/default/base/img/og-image.jpg":
                        start = start -1
                    if  "zawya.com" in entry.link and img_src == "https://www.zawya.com/resources/img/zawya-logo-en-social.png":
                        start = start -1

                if 'end' in value:
                    if "bbc.com" in entry.link and len(list_paragraphs)<=5:
                        end = len(list_paragraphs)
                    else:
                        end = len(list_paragraphs)-int(value['end'])
                selected_lines = list_paragraphs[start:end]

                final_article = " ".join(selected_lines)
                final_title = entry.title
                clean_list = cleaner_list + value['exclude']

                for phrase in clean_list:
                    final_article = final_article.replace(phrase, '')
                    final_title = final_title.replace(phrase, '')
                
                if "wam.ae" in entry.link:
                    final_article = re.sub(r'^.*? -', '', final_article)
                elif "nytimes.com" in entry.link:
                    final_article = re.sub(r'^.*? —', '', final_article)
                elif "wsj.com" in entry.link:
                    final_article = re.sub(r'^.*?—', '', final_article)
                elif "reuters.com" in entry.link:
                    final_article = re.sub(r'^.*? -', '', final_article)
                elif "theguardian.com" in entry.link:
                    final_article.replace('\u00a0', '')
                    final_article = re.sub(r'^.*?GMT', '', final_article)
                elif "washingtonpost.com" in entry.link:
                    final_article = re.sub(r'^.*? —', '', final_article)
                elif "indianexpress.com" in entry.link:
                    final_article = re.sub(r'^.*? -', '', final_article)
                elif "caixin.com" in entry.link:
                    final_article = re.sub(r'^.*? —', '', final_article)
                    final_article = final_article.split('Gallery :', 1)[0]
                elif "dawn.com" in entry.link:
                    final_article = re.sub(r'^.*?: ', '', final_article)
                elif "gulfnews.com" in entry.link:
                    final_article = re.sub(r'^.*?: ', '', final_article)
                elif "inquirer.com" in entry.link:
                    final_article.replace('\u00a0', '')
                    final_article = re.sub(r'^.*? — ', '', final_article)
                    final_article = re.sub(r'^.*?--', '', final_article)
                elif "thenews.com.pk" in entry.link:
                    final_article = re.sub(r'^.*?: ', '', final_article)
                elif "onmanorama.com" in entry.link:
                    final_article = re.sub(r'^.*?: ', '', final_article)
                elif "zawya.com" in entry.link:
                    final_article = re.sub(r'^.*?: ', '', final_article)
                    final_article = re.sub(r'^.*?- ', '', final_article)
                    final_article = re.sub(r'^.*? —', '', final_article)
                final_summary = summarize(final_article, word_count = 60)
                wordcount = sum([i.strip(string.punctuation).isalpha() for i in final_summary.split()])
                if wordcount <=50:
                    final_summary = summarize(final_article, word_count = 70)
                    wordcount2 = sum([i.strip(string.punctuation).isalpha() for i in final_summary.split()])
                    if wordcount2 <= 50:
                        final_summary = summarize(final_article, word_count = 75)
                model = gensim.models.Doc2Vec.load('saved_doc2vec_model')  
                model.docvecs.most_similar(
                    positive=[
                        model.infer_vector(final_summary)
                    ],
                    topn=5
                )

                # Article URL
                article['url'] = entry.link.split('?', 1)[0]
                # MD5 id
                article['id'] = hashlib.md5((article['url'] + final_title).encode('utf-8')).hexdigest()
                # Article image
                article['img'] = img_src
                # Article titles
                article['title'] = final_title
                # article['title_a'] = google_translator().translate(final_title,lang_tgt = 'ar')
                # Article sources
                article['src'] = value['source_en']
                # article['src_a'] = value['source_ar']
                # Article text and summaries
                article['txt'] = final_article
                article['summary'] = final_summary
                # article['summary_a'] = google_translator().translate(final_summary,lang_tgt = 'ar')
                # Article timestamp
                article['timestamp'] = str(timestamp)
                # Article read-time
                article['readtime'] = str(ceil(readtime.of_text(final_article).seconds/60))
                # Article category
                article['category'] = value['category']
                article['language'] = value['language']
                article['isSeen'] = "n"

                if article != {}:
                    try:
                        table.put_item(Item = article, ConditionExpression='attribute_not_exists(id)')
                        # SENDING FIREBASE CLOUD-MESSAGING NOTIFICATION
                        notification_headers = {
                            'Content-Type': 'application/json',
                            'Authorization': 'key=' + serverToken,
                        }
                        body_en = {
                            'notification': {
                                    'title': 'BREAKING NEWS: ' + article['src'],
                                    'body': article['title'],
                                    'click_action': 'FLUTTER_NOTIFICATION_CLICK',
                                    'sound': 'default'
                            },
                            'to': deviceToken,
                            'priority': 'high',
                            'content_available': 'true',
                        }
                        response_en = requests.post(
                            "https://fcm.googleapis.com/fcm/send", 
                            headers = notification_headers, 
                            data = json.dumps(body_en)
                        )
                        print("--Added to DynamoDB")
                    except ClientError as e:
                        print("--Not added, already present")
            except Exception as e:
                print("--Download Failed. Continuing...")
    return newsPaper
