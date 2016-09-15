from bs4 import BeautifulSoup
from telepot.namedtuple import InlineKeyboardMarkup, InlineKeyboardButton

import telepot
import time
import aiohttp
import random
import asyncio
import commons
import urllib.request
import functools

VERSION = "1.1.0"
AUTHORS = ['Clarence', 'Beiyi', 'Yuxin', 'Joel', 'Qixuan']
LOG_TAG = "bot"

REPO_URL = "https://github.com/clarencecastillo/ntu-campusbot"
CAM_BASE_IMAGE_URL = "https://webcam.ntu.edu.sg/upload/slider/"
NTU_WEBSITE = "http://www.ntu.edu.sg/"
SHUTTLE_BUS_URL = "has/Transportation/Pages/GettingAroundNTU.aspx"
NEWS_HUB_URL = "http://news.ntu.edu.sg/Pages/NewsSummary.aspx?Category=news+releases"
NEWS_COUNT = 5
HTTP_REQUEST = 60

HELP_MESSAGE = '''
You can control this bot by sending these commands:

/peek - get current screenshot of a location
/news - get latest news from NTU News Hub
/subscribe - subscribe to NTU's official twitter account feed
/unsubscribe - unsubscribe from NTU's official twitter account feed
/shuttle - get info about NTU internal shuttle bus routes
/about - get info about this bot
'''

START_MESSAGE = '''
Thank you for using <b>NTU_CampusBot</b>!

I can help you fetch the latest news from NTU News Hub and also check for crowded \
areas around the campus so you can effectively plan your stay.

<b>DISCLAIMER</b>
<code>This bot is for informational purposes only. Use of NTU surveillance is \
governed by the university and may be subject to change without prior notice. \
If you find a bug, or notice that NTU_CampusBot is not working, please file a \
New Issue on Github.</code> [<a href='%s'>link</a>]

<b>NOTES</b>
<code>Timestamp shown of the snapshot image may not accurately reflect the camera's \
view at the time of request. You may notice a slight desynchronization due to \
the fixed refresh rate of the cameras.</code>

To check available commands, use /help
''' % (REPO_URL)

ABOUT_MESSAGE = '''
====================
<b>NTU_CampusBot</b>   v<b>%s</b>
====================

Made with %s by:
<b>%s</b>
'''

PEEK_MESSAGE = "Which location should I peek for you?"
SHUTTLE_MESSAGE = "Get info about which shuttle bus service?"
NEWS_WAIT_MESSAGE = "Fetching latest news. Please wait."
INVALID_COMMAND_MESSAGE = "Say again? I didn't quite catch that."
ALREADY_SUBSCRIBED_MESSAGE = "You are already subscribed to receive the latest tweets from NTU's official Twitter account! Wanna unsub? /unsubscribe"
NOT_SUBSCRIBED_MESSAGE = "You are not subscribed to receive the latest tweets from NTU's official Twitter account! Wanna sub? /subscribe"
SUCCESSFULLY_SUBSCRIBED = "Successfully subscribed to NTU's official Twitter account! Wanna unsub? /unsubscribe"
SUCCESSFULLY_UNSUBSCRIBED = "Successfully unsubscribed from NTU's official Twitter account! Wanna sub back? /subscribe"

BUS_SERVICES = {}
LOCATIONS = {
    "Fastfood Level, Admin Cluster": "fastfood",
    "School of Art, Design and Media": "adm",
    "Lee Wee Nam Library": "lwn-inside",
    "Quad": "quad",
    "Walkway between North and South Spines": "WalkwaybetweenNorthAndSouthSpines",
    "Canteen B": "canteenB",
    "Onestop@SAC": "onestop_sac"
}

CALLBACK_COMMAND_LOCATION = "location"
CALLBACK_COMMAND_BUS = "bus"
LOCATIONS_KEYBOARD = None
BUS_SERVICES_KEYBOARD = None

def init():

    global LOCATIONS_KEYBOARD
    global BUS_SERVICES_KEYBOARD

    LOCATIONS_KEYBOARD = InlineKeyboardMarkup(inline_keyboard = [
        [InlineKeyboardButton(text = key, callback_data = CALLBACK_COMMAND_LOCATION + ":" + key)]
        for key in LOCATIONS.keys()
    ])
    commons.log(LOG_TAG, "locations keyboard ready")

    shuttle_bus_page = urllib.request.urlopen(NTU_WEBSITE + SHUTTLE_BUS_URL).read()
    for service in BeautifulSoup(shuttle_bus_page, "html.parser").find_all("span", {"class": "route_label"}):

        service_name = service.string.strip()
        shuttle_bus_info_page = urllib.request.urlopen(NTU_WEBSITE + service.find_next_sibling("a")['href']).read()

        shuttle_bus_route = ""
        sub_routes = service.parent.find_all("strong")

        # workaround for inconsistent route layouting for campus rider service
        if len(service.parent.find_all("span")) == 2: del sub_routes[-1]

        # function to get list of bus stops given a header
        parse_bus_stops = lambda element: "\n".join([str(index + 1) + ". " + bus_stop.string for index, bus_stop in enumerate(element.find_next("ul").find_all("li"))])

        if len(sub_routes):
            # combine all sub routes (as combination of the sub route header with its list) with other sub routes
            shuttle_bus_route = "".join(["\n<b>" + sub_route.string + "</b>\n" + parse_bus_stops(sub_route) for sub_route in sub_routes])
        else :
            # just a list of bus stops without any sub route header
            shuttle_bus_route = parse_bus_stops(service)

        BUS_SERVICES[service_name] = {
            # scrape bus service image url
            "image_url": BeautifulSoup(shuttle_bus_info_page, "html.parser").find("div", {"class": "img-caption"}).img['src'],
            # bus route information
            "info": "<b>%s</b>\n\n<b>ROUTE</b>\n%s" % (service_name.upper(), shuttle_bus_route)
        }

    BUS_SERVICES_KEYBOARD = InlineKeyboardMarkup(inline_keyboard = [
        [InlineKeyboardButton(text = key, callback_data = CALLBACK_COMMAND_BUS + ":" + key)] for key in BUS_SERVICES.keys()
    ])
    commons.log(LOG_TAG, "bus services keyboard ready")

class NTUCampusBot(telepot.aio.helper.ChatHandler):

    def __init__(self, *args, **kwargs):
        super(NTUCampusBot, self).__init__(*args, **kwargs)

    def _send_news(self, chat, future):

        soup = BeautifulSoup(future.result(), "html.parser")
        next_news = soup.find_all("div", {"class": "ntu_news_summary_title_first"})[0]
        for i in range(NEWS_COUNT):
            news_title = next_news.a.string.strip().title()
            news_link = next_news.a['href']
            news_date = next_news.next_sibling.string

            news_message = "<b>%s</b>\n<a href='%s'>%s</a>" % (news_date, news_link, news_title)
            asyncio.ensure_future(self.sender.sendMessage(news_message, parse_mode = 'HTML'))

            next_news = next_news.find_next_sibling("div", {"class": "ntu_news_summary_title"})

        future.remove_done_callback(self._send_news)
        self._log("sent " + str(NEWS_COUNT) + " news items", chat)

    def _log(self, message, chat):
        sender = chat['title' if 'title' in chat else 'username']
        commons.log(LOG_TAG, "[" + sender + ":" + str(chat['id']) + "] " + message)

    async def _load_url(self, url, timeout):
        response = await aiohttp.get(url)
        return (await response.text())

    async def _start(self, is_admin):

        if (is_admin):
            await self.sender.sendMessage("Hi Admin!")
        else:
            await self.sender.sendMessage(START_MESSAGE, parse_mode = 'HTML', disable_web_page_preview = True)
            await self._subscribe()

    async def _peek(self, is_admin):
        global LOCATIONS_KEYBOARD
        await self.sender.sendMessage(PEEK_MESSAGE, reply_markup = LOCATIONS_KEYBOARD)

    async def _help(self, is_admin):
        await self.sender.sendMessage(HELP_MESSAGE, parse_mode = 'HTML')

    async def _fetch_news(self, is_admin):
        await self.sender.sendMessage(NEWS_WAIT_MESSAGE)

        chat = await self.administrator.getChat()
        future = asyncio.ensure_future(self._load_url(NEWS_HUB_URL, HTTP_REQUEST))
        future.add_done_callback(functools.partial(self._send_news, chat))

    async def _about(self, is_admin):

        author_names = "\n".join(random.sample(AUTHORS, len(AUTHORS)))
        heart_icon = u'\U00002764'
        await self.sender.sendMessage(ABOUT_MESSAGE % (VERSION, heart_icon, author_names), parse_mode = 'HTML')

    async def _subscribe(self, is_admin):

        chat = await self.administrator.getChat()
        chat_id = chat['id']

        if chat_id not in commons.subscribers:
            commons.new_subscriber(chat_id, chat['title' if 'title' in chat else 'username'])
            await self.sender.sendMessage(SUCCESSFULLY_SUBSCRIBED)
        else:
            await self.sender.sendMessage(ALREADY_SUBSCRIBED_MESSAGE)

    async def _unsubscribe(self, is_admin):

        chat = await self.administrator.getChat()
        chat_id = chat['id']

        if chat_id in commons.subscribers:
            commons.remove_subscriber(chat_id, chat['title' if 'title' in chat else 'username'])
            await self.sender.sendMessage(SUCCESSFULLY_UNSUBSCRIBED)
        else:
            await self.sender.sendMessage(NOT_SUBSCRIBED_MESSAGE)

    async def _shuttle_bus(self, is_admin):
        global BUS_SERVICES_KEYBOARD
        await self.sender.sendMessage(SHUTTLE_MESSAGE, reply_markup = BUS_SERVICES_KEYBOARD)

    async def _broadcast(self, message, is_admin):
        if message:
            for subscriber_id in commons.subscribers:
                await self.bot.sendMessage(subscriber_id, message)

    async def on_chat_message(self, message):
        if("text" not in message): return
        command, _, payload = message['text'][1:].partition(" ")

        chat = await self.administrator.getChat()
        self._log("chat: " + message['text'], chat)

        is_admin = chat['id'] in commons.shared['admins']

        if command.startswith("start"):
            await self._start(is_admin)
        elif command.startswith("peek"):
            await self._peek(is_admin)
        elif command.startswith("news"):
            await self._fetch_news(is_admin)
        elif command.startswith("help"):
            await self._help(is_admin)
        elif command.startswith("about"):
            await self._about(is_admin)
        elif command.startswith("subscribe"):
            await self._subscribe(is_admin)
        elif command.startswith("unsubscribe"):
            await self._unsubscribe(is_admin)
        elif command.startswith("shuttle"):
            await self._shuttle_bus(is_admin)
        elif command.startswith("broadcast"):
            await self._broadcast(payload, is_admin)
        elif message['text'].startswith("/"):
            await self.sender.sendMessage(INVALID_COMMAND_MESSAGE)

    async def on_callback_query(self, message):

        callback_id = message['id']
        message_payload = message['data'].split(":")
        command = message_payload[0]
        parameter = message_payload[1]

        chat = await self.administrator.getChat()
        self._log("callback - " + message['data'], chat)

        await self.bot.answerCallbackQuery(callback_id, text = 'Fetching data. Please wait.')
        image_url = ""
        response_message = ""
        if (command == CALLBACK_COMMAND_BUS):
            image_url = NTU_WEBSITE + BUS_SERVICES[parameter]["image_url"]
            response_message = BUS_SERVICES[parameter]["info"]
        else:
            image_url = CAM_BASE_IMAGE_URL + LOCATIONS[parameter] + ".jpg?rand=" + str(time.time())
            response_message = time.strftime("%a, %d %b %y") + " - <b>" + parameter + "</b>"

        await self.sender.sendMessage(response_message, parse_mode='HTML')
        asyncio.ensure_future(self.sender.sendPhoto(image_url))

    async def on__idle(self, event):
        chat = await self.administrator.getChat()
        self._log("session expired", chat)
        self.close()
