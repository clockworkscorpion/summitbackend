#Flask imports
from flask import Flask, request, jsonify
# from flask_dynamo import Dynamo
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
# from google_trans_new import google_translator

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

header_bloomberg = {
    'Host':'www.bloomberg.com',
    'User-Agent':'Mozilla/5.0 (compatible; Googlebot/2.1; +http://google.com/bot.html)',
    'Accept':'*/*',
    'Accept-Language':'en-US,en;q=0.9',
    'Accept-Encoding':'gzip, deflate, br',
    'Referer':'https://www.google.com',
    'DNT':'1',
    'Connection':'keep-alive',
    'TE':'Trailers'
}

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
    "COPYRIGHT 2020 MANORAMA ONLINE.",
    "ALL RIGHTS RESERVED.",
    "external-link",
    "\nAD\n",
    "\n",
    "\t",
    "\r",
    " - Reuters India",
    " - Reuters UK",
    " - Reuters",
    "Onmanorama Staff",
    " Try Again ! ",
    "What\u2019s the background:",
    "What\u2019s new:",
    " - Bloomberg",
    " - Caixin Global",
    " - mediaoffice.ae",
    " CC\\nADVERTISEMENT\\n \\n\\n",
    "ADVERTISEMENT",
    " CC\\n",
    " [ac]",
    ": Markets Wrap",
    "SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY",
    " - ZAWYA",
    " -Aa +",
    "What\u2019s new",
    "OR",
    "(link in Chinese) ",
    ", Crown Prince of Abu Dhabi and Deputy Supreme Commander of the Armed Forces",
    "In his capacity as ",
    "Ruler of Dubai, Vice President and Prime Minister of the UAE",
    ", Vice President and Ruler of Dubai",
    "IANS",
    # "Covid-19: ",
    # "COVID-19: ",
    # "Coronavirus: ",
    # "COVID: ",
    "Coronavirus | ",
    "Coronavirus live updates | ",
    "Daily Briefing: ",
    "Top Stories"
]

dxbmo_imglist = [
    "/-/media/news-banner/newsbanner_mobile.jpg?h=433&w=642&hash=700E11E23F066ED3A4853CFD3DC9E41F",
    "/-/media/news-banner/newsbanner.jpg?h=2786&w=7676&hash=89675509E5A8B37D879D91347860D55E",
    "/-/media/feature/navigation/logo/logo.png",
    "/-/media/feature/navigation/logo/god-logo.png",
    "/-/media/feature/navigation/footer/government-logo.png",
    "/-/media/feature/navigation/footer/dubai-logo.png",
    "/assets/svgs/logo.svg",
    "/assets/svgs/rotate.gif",
    ""
]

s3 = boto3.resource('s3')
dynamodb = boto3.resource('dynamodb', region_name = 'ap-south-1')
table = dynamodb.Table('news')

serverToken = "AAAAIIZZRxw:APA91bFL0N7NkwJFnGqvcOCws4DMdF8jxc9jH2XkFQm0pS599i3JiQW0pK4SXX6MhPc2Gs3peJxF9ZCFUuvVCmCe235ezbo61BNqPUTtq-HrsRusYmgMBs3ezNxFS0C4sKPqBf0bURan"
deviceToken = "cjh9LOcJRXqNzqiFEvxTQP:APA91bEJA9yxAgA36Erm5L_7CJTm8YNhGYCyslqZ5JTC-ZHuemNir1lYn3paxQBtBPuKqG1JltOx6ATKoTio748GQrse-QjiZBspmWYeV7MLrAHAbNYorD-XQCwpv41L6vl-PRiqzUuF"

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

                        #exclude sentences containing the following phrases
                        if paragraph not in excludeTexts \
                        and "FILE " not in paragraph \
                        and "OTHER WIDGETS" not in paragraph \
                        and "EditorsNote:" not in paragraph \
                        and "Last modified" not in paragraph \
                        and "illustrative purposes" not in paragraph \
                        and "WATCH MORE" not in paragraph \
                        and "READ MORE" not in paragraph \
                        and "Video," not in paragraph \
                        and "BBC World Service" not in paragraph \
                        and "Author:" not in paragraph \
                        and not ("BBC News" in paragraph and "By" in paragraph) \
                        and "Contact " not in paragraph \
                        and "Advent calendar: " not in paragraph \
                        and "Published in Dawn" not in paragraph \
                        and "Permalink " not in paragraph \
                        and "Printable version" not in paragraph \
                        and "Photo from " not in paragraph \
                        and "INQUIRER file photo " not in paragraph \
                        and "FEATURED STORIES" not in paragraph \
                        and "NEWSINFO" not in paragraph \
                        and "(We will not stop improving especially with the coming Christmas season in our efforts to combat COVID-19 and in strengthening our health system.)" not in paragraph \
                        and "Image: " not in paragraph \
                        and "By Africanews" not in paragraph \
                        and "pic.twitter.com" not in paragraph \
                        and "Also read: " not in paragraph \
                        and "Onmanorama Staff" not in paragraph \
                        and " contributed reporting." not in paragraph \
                        and " contributed to this report." not in paragraph \
                        and " Min Read" not in paragraph \
                        and "Reporting by " not in paragraph \
                        and "Image Credit:" not in paragraph \
                        and "Photos credit: " not in paragraph \
                        and "GMT\\n" not in paragraph \
                        and " reported from " not in paragraph \
                        and "Watch more: " not in paragraph \
                        and "Read more: " not in paragraph \
                        and "This clip is from " not in paragraph \
                        and "From the section " not in paragraph \
                        and "Listen to " not in paragraph \
                        and "Producer / Editor: " not in paragraph \
                        and "With assistance by " not in paragraph \
                        and "Write to " not in paragraph \
                        and "https:" not in paragraph \
                        and "http:" not in paragraph \
                        and "KT Morning Chat" not in paragraph \
                        and "Exclusive:" not in paragraph \
                        and "Special:" not in paragraph \
                        and "News in a Minute:" not in paragraph \
                        and "Edited by" not in paragraph \
                        and "Read more" not in paragraph \
                        and "\u00a0Read More\u00a0" not in paragraph \
                        and "read more" not in paragraph \
                        and "In Pictures" not in paragraph \
                        and "SyndiGate Media Inc." not in paragraph \
                        and "Visual journalist" not in paragraph \
                        and "Produced and edited by " not in paragraph \
                        and "Graphics by " not in paragraph \
                        and "This video was first published in " not in paragraph \
                        and "Science correspondent" not in paragraph \
                        and "BBC music reporter" not in paragraph \
                        and "Video by" not in paragraph \
                        and "Trending Stories" not in paragraph \
                        and "Source " not in paragraph \
                        and "LOOK:" not in paragraph \
                        and "RELATED STORIES:" not in paragraph \
                        and "WATCH:" not in paragraph \
                        and "Photo By" not in paragraph \
                        and "Gallery:" not in paragraph \
                        and "Image courtesy" not in paragraph \
                        and "contributed to this article." not in paragraph \
                        and "Appeared in" not in paragraph \
                        and "@" not in paragraph \
                        and not((p == 0 or p == 1 or p == 2)  and "By" in paragraph):
                            list_paragraphs.append(paragraph)
                            list_paragraphs = [x for x in list_paragraphs if x!= '']
                            list_paragraphs = [x for x in list_paragraphs if x!= ' ']
                
                start = 0
                end = len(list_paragraphs)
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
                # final_summary = summarize(final_article, word_count = 60)
                # wordcount = sum([i.strip(string.punctuation).isalpha() for i in final_summary.split()])
                # if wordcount <=50:
                #     final_summary = summarize(final_article, word_count = 70)
                #     wordcount2 = sum([i.strip(string.punctuation).isalpha() for i in final_summary.split()])
                #     if wordcount2 <= 50:
                #         final_summary = summarize(final_article, word_count = 75)
                # model = gensim.models.Doc2Vec.load('saved_doc2vec_model')  
                # new_sentence = "I opened a new mailbox".split(" ")  
                # model.docvecs.most_similar(positive=[model.infer_vector(new_sentence)],topn=5)

                final_summary = ' '.join(re.split(r'(?<=[.])\s', final_article)[:3])
                
                wordcount = sum([i.strip(string.punctuation).isalpha() for i in final_summary.split()])
                if wordcount >= 75:
                    final_summary = ' '.join(re.split(r'(?<=[.])\s', final_article)[:2])
                elif wordcount <= 60:
                    final_summary = ' '.join(re.split(r'(?<=[.])\s', final_article)[:4])
                wordcount = sum([i.strip(string.punctuation).isalpha() for i in final_summary.split()])
                if wordcount >= 75: 
                    final_summary = ' '.join(re.split(r'(?<=[.])\s', final_article)[:1])
                if final_summary[0] == ' ':
                    final_summary = final_summary[1:]

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
                        # SENDING FCM NOTIFICATION
                        # notification_headers = {
                        #     'Content-Type': 'application/json',
                        #     'Authorization': 'key=' + serverToken,
                        # }
                        # body_en = {
                        #     'notification': {
                        #             'title': 'BREAKING NEWS: ' + article['src'],
                        #             'body': article['title'],
                        #             'click_action': 'FLUTTER_NOTIFICATION_CLICK',
                        #             'sound': 'default'
                        #     },
                        #     'to': deviceToken,
                        #     'priority': 'high',
                        #     'content_available': 'true',
                        # }
                        # response_en = requests.post(
                        #     "https://fcm.googleapis.com/fcm/send", 
                        #     headers = notification_headers, 
                        #     data = json.dumps(body_en)
                        # )
                        print("--Added to DynamoDB")
                    except ClientError as e:
                        print("--Not added, already present")
            except Exception as e:
                print("--Download Failed. Continuing...")
    return newsPaper

# SCHEDULED FUNCTION
def newsbuilder():
    # data = {}
    # data['newspapers'] = {}
    # websites =[]
    #  Loads the JSON files with news sites
    # with open('NewsPapers.json') as data_file:
    #     json_content = json.load(data_file)
    content_object = s3.Object('newsapi-bucket', 'NewsPapers.json')
    file_content = content_object.get()['Body'].read().decode('utf-8')
    json_content = json.loads(file_content)

    # BEGIN FAN-OUT
    for website, value in json_content.items():
        # Parse the RSS feed to get individual links
        print("\n\nDownloading articles from ", website)
        newsPaper = {
            "rss": value['rss'],
            "articles": []
        }
        if website == "thenational":
            newsPaper['articles'] = jsonparser(value)
            # newsPaper['count'] = len(newsPaper['articles'])
        else:
            newsPaper['articles'] = rssparser(value)
            # newsPaper['count'] = len(newsPaper['articles'])
        # data['newspapers'][website] = newsPaper
        continue
    # Finally it saves the articles as a JSON-file.
    try:
        print("Scheduled Function run successfully!")
        # return jsonify(data)
    except Exception as e:
        print("--Error! JSON not compiled!")

@app.route('/api', methods=['GET', 'PATCH', 'POST'])
def API():
    if request.method == 'GET':
        starttime = time()
        # lang = str(request.args['lang'])
        data = {}
        data['articles'] = {}
        list_articles = []
        # queryCount = 1
        time_8hdiff = str(int(time() - 28800))
        # Make Initial Query
        response = table.query(
            IndexName = 'time-index',
            KeyConditionExpression=Key('isSeen').eq("n") & Key('timestamp').gte(time_8hdiff),
        )
        # Extract the Results
        articles = response['Items']
        for article in articles:
            list_articles.append(article)
            # print(str(article['title']))    
        # queryCount += 1
        while 'LastEvaluatedKey' in response:
            # print('---------')
            key = response['LastEvaluatedKey']
            response = table.query(
                IndexName = 'time-index',
                KeyConditionExpression=Key('isSeen').eq("n") & Key('timestamp').gte(time_8hdiff),
                ExclusiveStartKey=key
           )
            articles = response['Items']
            for article in articles:
                list_articles.append(article)
                # print(str(article['title']))
            # queryCount += 1
        # print("---------")
        # Finally it saves the articles as a JSON-file.
        data['articles'] = list_articles
        try:
            print('\nTotal Time Elapsed:',time() - starttime)
            return jsonify(data)
        except Exception as e:
            print("--Error! JSON not compiled!")

    elif request.method == 'PATCH':
        isEdited = str(request.args['isEdited'])
        data = request.get_json()
        key = {
            'id': data['id'],
            'timestamp': data['timestamp']
        }
        if isEdited == "y":
            try:
                response = table.update_item(
                    Key = key,
                    UpdateExpression = "SET title=:t, summary=:s, category=:c, img=:i",
                    ExpressionAttributeValues = {
                        ':t': data['title'],
                        ':s': data['summary'],
                        ':c': data['category'],
                        ':i': data['img']
                    },
                    ReturnValues="UPDATED_NEW"
                )
                return jsonify(response)
            except Exception as e:
                return jsonify("ITEM NOT EDITED")
        elif isEdited == "n":
            try:
                response = table.update_item(
                    Key = key,
                    UpdateExpression = "SET isSeen=:e",
                    ExpressionAttributeValues = {
                        ':e': 'y'
                    },
                    ReturnValues="UPDATED_NEW"
                )
                return jsonify(response)
            except ClientError as e:
                return jsonify("ITEM iSSEEN UNCHANGED")

    elif request.method == 'POST':
        data = request.get_json()
        key = {
            'id': data['id'],
            'timestamp': data['timestamp']
        }
        try:
            response = table.delete_item(Key = key)
            return jsonify(response)
        except ClientError as e:
            return jsonify("ITEM NOT DELETED")
    
    else:
        return jsonify("No data found")

if __name__ == '__main__':
    app.run()