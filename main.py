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
from selenium.common.exceptions import TimeoutException

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
        chrome_options.add_argument("--headless=new")

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

            # Navigate to RC Status page
            driver.get("https://services.parivahan.gov.in/ntr/rc-status")
            print(f"DEBUG: Page loaded, title={driver.title!r}, url={driver.current_url}")

            # Wait for Angular to fully render the page
            import time
            time.sleep(3)

            # Try to find registration number inputs using Angular selectors
            print("DEBUG: Waiting for registration number inputs...")
            try:
                # Try common Angular input selectors
                first = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[formcontrolname='regNo1'], input[ng-model='vm.regNo1'], #regNo1"))
                )
                print("DEBUG: Found regNo1 input")
                first.send_keys(first_p)

                second = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[formcontrolname='regNo2'], input[ng-model='vm.regNo2'], #regNo2"))
                )
                print("DEBUG: Found regNo2 input")
                second.send_keys(second_p)
            except Exception as e:
                print(f"DEBUG: Angular inputs not found, trying old JSF selectors: {e}")
                try:
                    first = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.ID, "form_rcdl:tf_reg_no1"))
                    )
                    print("DEBUG: Found tf_reg_no1")
                    first.send_keys(first_p)
                    second = driver.find_element(By.ID, "form_rcdl:tf_reg_no2")
                    second.send_keys(second_p)
                except Exception as e2:
                    print(f"DEBUG: JSF inputs also not found: {e2}")
                    raise Exception("Could not find registration number inputs on the page")

            print(f"DEBUG: Filled inputs, searching for captcha container...")

            # Try multiple selectors for the captcha container (Angular version)
            image_main = None
            for sel in [
                # Angular-specific selectors
                (By.CSS_SELECTOR, "div.captcha-container img, div.captcha img, img.captcha-image"),
                (By.CSS_SELECTOR, "#captchaImage, img#captcha, img[src*='captcha']"),
                (By.XPATH, "//img[contains(@src,'captcha') or contains(@class,'captcha')]"),
                # Fallback to old selectors
                (By.CSS_SELECTOR, "table.vahan-captcha img"),
                (By.CSS_SELECTOR, "table.captcha img"),
            ]:
                try:
                    image_main = WebDriverWait(driver, 8).until(
                        EC.presence_of_element_located(sel)
                    )
                    print(f"DEBUG: Found captcha container via {sel}")
                    break
                except TimeoutException:
                    continue

            if image_main is None:
                print("DEBUG: Captcha container not found, dumping page source")
                with open(f"debug_{message.chat.id}.html", "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
                raise Exception("Captcha container not found")

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
            import traceback
            print(f"Error during scrape setup: {e}")
            print(f"DEBUG: Full traceback:\n{traceback.format_exc()}")
            try:
                driver.save_screenshot(f"debug_{message.chat.id}.png")
                print(f"DEBUG: Saved screenshot debug_{message.chat.id}.png")
            except Exception:
                pass
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
        # Find captcha input — try Angular-specific selectors first
        try:
            third = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[formcontrolname='captcha'], input[ng-model='vm.captcha'], #captchaInput"))
            )
            print("DEBUG: Found Angular captcha input")
        except Exception:
            # Try to find captcha input within the container
            try:
                third = image_main.find_element(By.CSS_SELECTOR, "input[type='text'], input[type='password']")
                print("DEBUG: Found captcha input in container")
            except Exception:
                # Fallback to old JSF selector
                try:
                    third = driver.find_element(By.ID, "form_rcdl:tf_captcha")
                    print("DEBUG: Using old JSF captcha input")
                except Exception:
                    # Try any input in the form
                    try:
                        form = driver.find_element(By.CSS_SELECTOR, "form")
                        third = form.find_element(By.TAG_NAME, "input")
                        print("DEBUG: Using any form input")
                    except Exception:
                        raise Exception("Captcha input not found")

        third.send_keys(captcha_text)
        third.send_keys(Keys.RETURN)

        try:
            # Try Angular result container first
            result_container = driver.find_element(By.CSS_SELECTOR, "div.result-container, div.vehicle-info, div.rc-details")
            response_text = result_container.text
            print(f"DEBUG: Found Angular result container with text: {response_text[:200]}...")
        except Exception:
            # Fallback to old JSF panel
            try:
                main = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "form_rcdl:rcPanel")))
                details = main.find_element(By.TAG_NAME, "table")
                response_text = details.text
                print(f"DEBUG: Using old JSF panel")
            except Exception as e:
                print(f"DEBUG: Could not find result container: {e}")
                response_text = ""

        # Try to parse JSON if present in page source
        try:
            json_data = driver.execute_script("return JSON.stringify(window.vehicleData || window.rcData || {})")
            if json_data:
                print(f"DEBUG: Found JSON data: {json_data[:200]}...")
                response_text = json_data
        except Exception:
            pass

        # Parse response based on format
        if response_text:
            # Try to extract JSON if present
            import json
            try:
                parsed = json.loads(response_text)
                if isinstance(parsed, dict):
                    response = json.dumps(parsed, indent=2)
                else:
                    response = str(parsed)
            except Exception:
                # Fallback to text parsing if not JSON
                response = sort(response_text.split("\n")) if '\n' in response_text else response_text
        else:
            response = "No vehicle information found"

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