#!/usr/bin/env python3
"""Script to verify BrightMind bot messages in Slack via API."""

import os
import time
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Load tokens from environment
BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")

client = WebClient(token=BOT_TOKEN)

def get_bot_dm_channel():
    """Find or create a DM channel with the bot itself (for testing)."""
    try:
        # Get bot's own user ID
        auth_response = client.auth_test()
        bot_user_id = auth_response["user_id"]
        print(f"Bot user ID: {bot_user_id}")
        
        # List all conversations
        conversations = client.conversations_list(types="im")
        
        # Find the first DM (instant message)
        for channel in conversations["channels"]:
            print(f"Found DM channel: {channel['id']}")
            return channel["id"]
        
        print("No DM channels found")
        return None
        
    except SlackApiError as e:
        print(f"Error getting DM channel: {e.response['error']}")
        return None

def get_recent_messages(channel_id, limit=10):
    """Get recent messages from a channel."""
    try:
        result = client.conversations_history(
            channel=channel_id,
            limit=limit
        )
        
        messages = result["messages"]
        print(f"\n=== Recent Messages in Channel {channel_id} ===")
        print(f"Found {len(messages)} messages\n")
        
        for i, msg in enumerate(reversed(messages), 1):
            user = msg.get("user", "bot")
            text = msg.get("text", "")
            timestamp = msg.get("ts", "")
            print(f"{i}. [{timestamp}] {user}: {text}")
        
        return messages
        
    except SlackApiError as e:
        print(f"Error getting messages: {e.response['error']}")
        return []

def send_test_message(channel_id, text):
    """Send a test message to a channel."""
    try:
        result = client.chat_postMessage(
            channel=channel_id,
            text=text
        )
        print(f"\n✓ Message sent: {text}")
        return result
        
    except SlackApiError as e:
        print(f"Error sending message: {e.response['error']}")
        return None

def main():
    print("=== Slack Message Verification ===\n")
    
    # Get DM channel
    dm_channel = get_bot_dm_channel()
    
    if not dm_channel:
        print("Could not find DM channel")
        return
    
    # Get existing messages
    print(f"\n1. Retrieving existing messages from DM...")
    messages = get_recent_messages(dm_channel)
    
    # Send test message
    print(f"\n2. Sending test message: 'What is Python?'")
    send_test_message(dm_channel, "What is Python?")
    
    # Wait for response
    print(f"\n3. Waiting 10 seconds for bot response...")
    time.sleep(10)
    
    # Get updated messages
    print(f"\n4. Retrieving updated messages...")
    updated_messages = get_recent_messages(dm_channel)
    
    print("\n=== Verification Complete ===")

if __name__ == "__main__":
    main()
