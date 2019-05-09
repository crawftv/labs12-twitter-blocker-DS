import tweepy
import re
from decouple import config
import json
import requests
import sys

def bert_request(tweet_text):
    data = {"description":tweet_text}
    headers= {'Content-type':"application/json",
               "cache-control":"no-cache"
              }
    data= json.dumps(data)
    return requests.post("http://35.192.71.216:5000/", data = data, headers = headers)

def process_tweet(full_tweet):
    #strip username
    tweet = full_tweet.full_text

    tweet = re.sub(r'(?<=^|(?<=[^a-zA-Z0-9-_\.]))@([A-Za-z]+[A-Za-z0-9-_]+)','',tweet)
    #strip newlines and unicode characters that aren't formatted
    tweet = re.sub(r'\n|&gt;|RT :','',tweet)
    #strip twitter urls from tweets
    tweet = re.sub(r'(?<=^|(?<=[^a-zA-Z0-9-_\.]))https://t.co/([A-Za-z0-9-_,\']+)','',tweet)
    #Remove emojis
    RE_EMOJI = re.compile('[\U00010000-\U0010ffff]', flags=re.UNICODE)
    tweet = RE_EMOJI.sub(r'', tweet)
    #remove whitespace
    tweet = tweet.strip()
    #make api request for toxicity analysis
    bert_result = bert_request(tweet).json()

    tweet_info = {"tweet":
                     {"user_id": full_tweet.user.id,
                      "user_name" : full_tweet.user.name,
                      "tweet": full_tweet.full_text,
                      "tweet_id" : full_tweet.id_str,
                     "bert_output": bert_result}
                    }
    return tweet_info


def clean_timeline(TWITTER_ACCESS_TOKEN,TWITTER_ACCESS_TOKEN_SECRET):
    # Create Twitter Connection
    twitter_auth = tweepy.OAuthHandler(config('TWITTER_CONSUMER_KEY'),config('TWITTER_CONSUMER_SECRET'))
    access_token = TWITTER_ACCESS_TOKEN
    access_token_secret = TWITTER_ACCESS_TOKEN_SECRET
    twitter_auth.set_access_token(access_token, access_token_secret)
    global TWITTER
    TWITTER = tweepy.API(twitter_auth)

    try:
        home_timeline = TWITTER.home_timeline(count=20,
                                         tweet_mode='extended',
                                         exlude_rts=False)
        timeline = [ process_tweet(full_tweet)
                   for full_tweet in home_timeline]
        return json.dumps(timeline)
	#error handling
    except tweepy.TweepError:
        print("tweepy.TweepError")

    except:
        e = sys.exc_info()[0]
        print("Error: %s" % e)


def process_request(request):
    """ Responds to a POST request with a list of dictionaries containing tweet
	id, text, user_id, user_name and bert results.
    """
    from flask import abort

    content_type = request.headers['content-type']
    request_json = request.get_json(silent=True)
    request_args = request.args

    if content_type == 'application/json': 
        request_json = request.get_json(silent=True)
        # TWITTER_ACCESS_TOKEN check/set/error
        if request_json and 'TWITTER_ACCESS_TOKEN' in request_json:
            TWITTER_ACCESS_TOKEN = request_json['TWITTER_ACCESS_TOKEN']
        else:
            raise ValueError("Missing a 'TWITTER_ACCESS_TOKEN'")
        # TWITTER_ACCESS_TOKEN_SECRET check/set/error
        if request_json and 'TWITTER_ACCESS_TOKEN_SECRET' in request_json:
            TWITTER_ACCESS_TOKEN_SECRET = request_json['TWITTER_ACCESS_TOKEN_SECRET']
        else:
            raise ValueError("Missing a 'TWITTER_ACCESS_TOKEN_SECRET'")

        # Call the function for the POST request. 
        if request.method == 'POST':
            return clean_timeline(TWITTER_ACCESS_TOKEN,TWITTER_ACCESS_TOKEN_SECRET)
    else:
        return abort(405)