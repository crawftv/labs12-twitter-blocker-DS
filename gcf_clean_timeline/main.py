import tweepy
import re
from decouple import config
import json
import requests
import sys
import asyncio
from concurrent.futures import ThreadPoolExecutor
import nest_asyncio
from itertools import zip_longest

nest_asyncio.apply()


def process_request(request):
    """ Responds to a GET request with "Hello world!". Forbids a PUT request.
    Args:
        request (flask.Request): The request object.
        <http://flask.pocoo.org/docs/1.0/api/#flask.Request>
    Returns:
        The response text, or any set of values that can be turned into a
         Response object using `make_response`
        <http://flask.pocoo.org/docs/1.0/api/#flask.Flask.make_response>.
    """
    from flask import abort

    content_type = request.headers["content-type"]
    request_json = request.get_json(silent=True)
    request_args = request.args

    if content_type == "application/json":
        request_json = request.get_json(silent=True)
        # TWITTER_ACCESS_TOKEN check/set/error
        if request_json and "TWITTER_ACCESS_TOKEN" in request_json:
            TWITTER_ACCESS_TOKEN = request_json["TWITTER_ACCESS_TOKEN"]
        else:
            raise ValueError("Missing a 'TWITTER_ACCESS_TOKEN'")
        # TWITTER_ACCESS_TOKEN_SECRET check/set/error
        if request_json and "TWITTER_ACCESS_TOKEN_SECRET" in request_json:
            TWITTER_ACCESS_TOKEN_SECRET = request_json["TWITTER_ACCESS_TOKEN_SECRET"]
        else:
            raise ValueError("Missing a 'TWITTER_ACCESS_TOKEN_SECRET'")

        if request_json and "num_pages" in request_json:
            num_pages = request_json["num_pages"]
        else:
            num_pages = 1

        # Call the function for the POST request.
        if request.method == "POST":
            establish_twitter_credentials(
                TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET
            )
            return execute_async_index_event_loop(num_pages)
    else:
        return abort(405)


def establish_twitter_credentials(TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET):
    """establish Twitter as as global. No need to pass it everytime.
    """
    twitter_auth = tweepy.OAuthHandler(
        config("TWITTER_CONSUMER_KEY"), config("TWITTER_CONSUMER_SECRET")
    )
    access_token = TWITTER_ACCESS_TOKEN
    access_token_secret = TWITTER_ACCESS_TOKEN_SECRET
    twitter_auth.set_access_token(access_token, access_token_secret)
    global TWITTER
    TWITTER = tweepy.API(twitter_auth)


def execute_async_index_event_loop(num_pages):
    """
    This function does something analogous to compiling the get_data_asynchronously function,
    Then it executes loop.
    1. Call the get_data_function
    2. Get the event_loop
    3. Run the tasks (Much easier to understand in python 3.7, "ensure_future" was changed to "create_task")
    4. Edge_list and top_interactions will be passed to the next functions
    """
    final_output = []
    mentions_timeline = get_mentions(final_output, num_pages)
    future = asyncio.ensure_future(
        get_index_data_asynchronous(final_output, num_pages, mentions_timeline)
    )
    loop = asyncio.get_event_loop()
    loop.run_until_complete(future)
    final_output = {"results": final_output}
    return json.dumps(final_output)


def get_mentions(final_output, num_pages):
    """
    Get tweets in which the user is mentioned.
    """
    try:
        home_timeline = TWITTER.mentions_timeline(
            count=32 * num_pages, tweet_mode="extended", exclude_rts=False
        )
        timeline = [process_tweet(full_tweet) for full_tweet in home_timeline]
        # create list of lists where sublists = 32 for BERT model
        z = grouper(timeline, 32)
        timeline = [[i for i in subz if i is not None] for subz in z]
        return timeline

    except tweepy.TweepError:
        print("tweepy.TweepError")

    except:
        e = sys.exc_info()[0]
        print("mentions_timeline: Error: %s" % e)


async def get_index_data_asynchronous(final_output, num_pages, mentions_timeline):
    """
    1. Establish an executor and number of workers
    2. Establish the session
    3. Establish the event loop
    4. Create the tasks. Add two lists together. (because as I understand appending adds the list inside of a list.)
        4a. tasks are created by list comprenhensions
    5. Gather tasks.
    """
    with ThreadPoolExecutor(max_workers=20) as executor:
        with requests.Session() as session:
            loop = asyncio.get_event_loop()
            tasks = [
                loop.run_in_executor(
                    executor, clean_timeline, *(session, final_output, page)
                )
                for page in range(num_pages)
            ] + [
                loop.run_in_executor(
                    executor, clean_mentions, *(session, sub_timeline, final_output)
                )
                for sub_timeline in mentions_timeline
            ]
            for response in await asyncio.gather(*tasks):
                pass


def clean_timeline(session, final_output, page):
    """
    1. Retrieve 32 tweets
    2. Prepare the tweet for BERT
    3. Execute the BERT analysis
    4. Add the results to the final_output
    """
    try:
        home_timeline = TWITTER.home_timeline(
            count=32,
            tweet_mode="extended",
            exlude_rts=False,
            exclude_replies=False,
            page=page,
        )
        home_timeline = [process_tweet(full_tweet) for full_tweet in home_timeline]
        output = bert_request(home_timeline)
        final_output += output

    except tweepy.TweepError:
        print("clean_timeline: tweepy.TweepError")

    except:
        e = sys.exc_info()[0]
        print("clean_timeline: Error: %s" % e)


def clean_mentions(session, sub_timeline, final_output):
    """
    Puts together the new BERT results with the final_output
    """
    final_output += bert_request(sub_timeline)


def process_tweet(full_tweet):
    """
    Prepare the tweet for the BERT model.
    """
    tweet = full_tweet.full_text
    # strip username
    tweet = re.sub(r"(?<=^|(?<=[^a-zA-Z0-9-_\.]))@([A-Za-z]+[A-Za-z0-9-_]+)", "", tweet)
    # strip newlines and unicode characters that aren't formatted
    tweet = re.sub(r"\n|&gt;|RT :", "", tweet)
    # strip twitter urls from tweets
    tweet = re.sub(
        r"(?<=^|(?<=[^a-zA-Z0-9-_\.]))https://t.co/([A-Za-z0-9-_,\']+)", "", tweet
    )
    # Remove emojis
    RE_EMOJI = re.compile("[\U00010000-\U0010ffff]", flags=re.UNICODE)
    tweet = RE_EMOJI.sub(r"", tweet)
    # remove whitespace
    tweet = tweet.strip()
    # make api request for toxicity analysis

    tweet_info = {
        "tweet": {
            "user_id": full_tweet.user.id,
            "user_name": full_tweet.user.name,
            "tweet": full_tweet.full_text,
            "tweet_id": full_tweet.id_str,
        }
    }
    return tweet_info


def grouper(iterable, n, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx
    args = [iter(iterable)] * n
    return zip_longest(fillvalue=fillvalue, *args)


def bert_request(sub_timeline):
    """
    1. Extract just the tweet from the sub_timeline
    2. Pass the list of tweets to the BERT function.
    3. Zip the original sub_timeline passed to the function
    4. Put the zip object into a dictionary
    """
    tweet_list = [tweet["tweet"]["tweet"] for tweet in sub_timeline]
    data = {"description": tweet_list, "max_seq_length": 32}
    headers = {"Content-type": "application/json", "cache-control": "no-cache"}
    data = json.dumps(data)
    results = requests.post(
        "http://35.222.5.199:5000/", data=data, headers=headers
    ).json()["results"]
    # results is a list comprehension of zipping tweet & bert_result lists
    # and making two dictionary key,values out of each.
    output = [
        {"tweet": t["tweet"], "bert_result": r} for t, r in zip(sub_timeline, results)
    ]
    return output
