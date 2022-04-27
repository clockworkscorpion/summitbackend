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

# SCHEDULED FUNCTION
def newsbuilder():
    # local testing classes
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
