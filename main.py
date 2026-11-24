import os
import re
import asyncio

# PRE-EMPTIVE FIX FOR PYTHON 3.15 + PYROGRAM COMPATIBILITY
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from aiohttp import web
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from process import check, get_captcha, sort
from creds import cred

# Initialize the client
app = Client(
    "Vehicle-Info-Bot",
    api_id=cred.API_ID,
    api_hash=cred.API_HASH,
    bot_token=cred.BOT_TOKEN
)

# Active Selenium sessions, keyed by chat id (driver, captcha container element)
sessions = {}

def find_chrome():
    """Locate the Chrome binary. Env override > Heroku buildpack > common paths."""
    if os.getenv("CHROME_BIN"):
        return os.getenv("CHROME_BIN")
    if os.path.exists("/app/.apt/usr/bin/google-chrome"):
        return "/app/.apt/usr/bin/google-chrome"
    for candidate in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ):
        if os.path.exists(candidate):
            return candidate
    return None

def chrome_service():
    """Build a ChromeService, or None to let Selenium auto-manage the driver."""
    path = os.getenv("CHROMEDRIVER_PATH")
    if path:
        return ChromeService(executable_path=path)
    if os.path.exists("/app/.chromedriver/bin/chromedriver"):
        return ChromeService(executable_path="/app/.chromedriver/bin/chromedriver")
    return None

@app.on_message(filters.command(["start"]))
async def start(client, message):
    print(f"DEBUG: Received /start from {message.from_user.first_name} (ID: {message.from_user.id})")
    try:
        await message.reply_text(
            text=f"`Hi` **{message.from_user.first_name}**\n`Enter the vehicle number to search`",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Help", callback_data="help"),
                InlineKeyboardButton("About", callback_data="about")
            ]])
        )
        print("DEBUG: Successfully sent reply to /start")
    except Exception as e:
        print(f"DEBUG: Failed to send reply: {e}")

@app.on_callback_query()
async def data(client, callback_query):
    txt = callback_query.data
    if txt == "help":
        await callback_query.message.edit(
            text="**How to use?**\n\nGive me the vehicle number as plain text without(,-,/..etc\nSuppose the vehicle number is KL-18-U-1234 then you need to enter it as kl18u1234 or KL18U1234\n\nWhile sending captcha you must send it as a reply to the given image\n\n__(Nb:vehicleinfobot is not affiliated to any of the government authorities)__",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Close ✖️", callback_data="close")]]))
    elif txt == "close":
        await callback_query.message.delete()
    elif txt == "about":
        await callback_query.message.edit(
            text=f"`Bot`            : [vehicleinfobot](t.me/vehicleinfobot)\n`Creator :` [agentnova](t.me/agentnova)\n`Language:` [Python3](https://python.org)\n`Library :` [Pyrogram](https://docs.pyrogram.org/),[Selenium](https://www.selenium.dev/) \n`Server  :` [Heroku](https://herokuapp.com/)",
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Give Feedback", url="t.me/agentnova")]]))

@app.on_message(filters.text & ~filters.reply)
async def errr(client, message):
    msg = message.text
    chek = check(msg)
    if chek == "invalid":
        await message.reply_text(
            text="Invalid format",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Help", callback_data="help")]])
        )
    elif chek == "valid":
        resp = await message.reply_text("Checking...", reply_to_message_id=message.id)
        r_num = message.text
        temp = re.compile("([a-zA-Z]+)([0-9]+)([a-zA-Z]+)([0-9]+)")
        res = temp.match(r_num).groups()
        first_p = res[0] + res[1] + res[2]
        second_p = res[3]

        print(f"Searching for: {first_p} - {second_p}")

        chrome_options = Options()
        chrome_bin = find_chrome()
        if chrome_bin:
            chrome_options.binary_location = chrome_bin

        # Anti-detection / stealth measures for cloud IPs
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--ignore-certificate-errors')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-web-security')
        chrome_options.add_argument('--disable-site-isolation-trials')
        chrome_options.add_argument('--disable-infobars')
        chrome_options.add_argument('--disable-notifications')
        chrome_options.add_argument('--disable-popup-blocking')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
        # Use headed mode on cloud (headless is easily detected)
        # chrome_options.add_argument("--headless=new")

        # Hide automation flags
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        try:
            service = chrome_service()
            driver = webdriver.Chrome(service=service, options=chrome_options) if service else webdriver.Chrome(options=chrome_options)

            # Hide webdriver property
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    window.chrome = { runtime: {} };
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                """
            })

            driver.get("https://parivahan.gov.in/rcdlstatus")

            first = driver.find_element(By.XPATH, "//input[@placeholder='DL10ABC']")
            first.send_keys(first_p)
            second = driver.find_element(By.XPATH, "//input[@placeholder='1234']")
            second.send_keys(second_p)
            image_main = driver.find_element(By.XPATH, "//table[@class='vahan-captcha inline-section']")
            image = image_main.find_element(By.TAG_NAME, "img")

            location = os.path.join("./CAPTCHA", str(message.chat.id))
            if not os.path.isdir(location):
                os.makedirs(location)

            get_captcha(driver, image, f"{location}/cap.png")
            await resp.delete()

            sessions[message.chat.id] = (driver, image_main)
            await message.reply_photo(
                photo=f"{location}/cap.png",
                caption="Type the captcha & reply to this message..",
                reply_markup=ForceReply()
            )

            if os.path.exists(f"{location}/cap.png"):
                os.remove(f"{location}/cap.png")
        except Exception as e:
            print(f"Error during scrape setup: {e}")
            await resp.edit(f"Error: {str(e)[:100]}")

@app.on_message(filters.reply)
async def ver(client, message):
    session = sessions.get(message.chat.id)
    if session is None:
        return

    driver, image_main = session
    await message.reply_to_message.delete()
    repl = await message.reply_text("`checking`")
    captcha_text = message.text

    try:
        third = image_main.find_element(By.TAG_NAME, "input")
        third.send_keys(captcha_text)
        third.send_keys(Keys.RETURN)

        main = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "form_rcdl:rcPanel")))
        details = main.find_element(By.TAG_NAME, "table")
        lst = details.text.split("\n")
        response = sort(lst)

        await message.delete()
        await repl.delete()
        await message.reply_text(text=f"{response}")
    except Exception as e:
        print(f"Error during verification: {e}")
        await message.delete()
        await repl.edit("__Reg.no does not exist or wrong captcha entered__")
    finally:
        driver.quit()
        sessions.pop(message.chat.id, None)

async def health_check(request):
    return web.Response(text="OK")

async def start_web_server():
    app_web = web.Application()
    app_web.router.add_get("/", health_check)
    runner = web.AppRunner(app_web)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Health server on port {port}")
    return runner

async def main():
    print("Starting bot...")
    await app.start()
    print("Bot is online! Press Ctrl+C to stop.")

    # Start health check server for Render Web Service
    runner = await start_web_server()

    await idle()

    await runner.cleanup()
    await app.stop()

if __name__ == "__main__":
    # Run on the same global loop Pyrogram captured at import time,
    # so its internal dispatcher tasks don't end up on a "different loop".
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
