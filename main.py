import requests
from critical_data import api_key, api_url
from google.transit import gtfs_realtime_pb2
from google.protobuf.json_format import MessageToJson

def fetch_realtime_data(api_url, api_key):
    headers = {'apiKey': api_key}
    try:
        resp = requests.get(api_url, headers=headers, timeout=10)
        resp.raise_for_status()
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(resp.content)
        return feed
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        return None

def main():
    feed = fetch_realtime_data(api_url, api_key)
    if not feed:
        print("Failed to retrieve data.")
        return

    # DEBUGGING
    json_str = MessageToJson(feed)
    print(json_str)

if __name__ == "__main__":
    main()