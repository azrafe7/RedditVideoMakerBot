import json
import re
from pathlib import Path
from typing import Dict, Final

from playwright.sync_api import ViewportSize, sync_playwright
from rich.progress import track

from utils import settings
from utils.console import print_step, print_substep
from utils.imagenarator import imagemaker
from utils.playwright import clear_cookie_by_name
from utils.videos import save_data  

import translators

import datetime as dt
import json
from jinja2 import Environment, FileSystemLoader

__all__ = ["download_screenshots_of_reddit_posts"]


def fill_template(template, values):
    filled_template = template # a copy of template
    for k, v in values.items():
        filled_template = filled_template.replace(k, v)

    return filled_template

# Formats `datetime` to something like '1 year ago', '25 minutes ago', etc.
# `style` can be one of ["none", "old_reddit", "new_reddit"]
# TODO: check if it works properly (for now it only tries to handle past dates)
def datetime_to_human_timedelta(datetime, style):
    if style == "none":
        return datetime

    now = dt.datetime.now()
    delta = now - datetime
    total_seconds = delta.total_seconds()
    years = total_seconds // (3600 * 24 * 30 * 12)
    months = total_seconds // (3600 * 24 * 30)
    days = total_seconds // (3600 * 24)
    hours = total_seconds // 3600
    minutes = total_seconds // 60
    seconds = total_seconds

    human_timedelta = "just now"
    if style == "old_reddit":
        suffixes = ["year", "month", "day", "hour", "minute", "second"]
        separator = " "
    elif style == "new_reddit":
        suffixes = ["y", "mo", "d", "h", "m", "s"]
        separator = ""
    elapsed = [years, months, days, hours, minutes, seconds]
    # print(list(zip(suffixes, elapsed)))
    for idx, t in enumerate(elapsed):
        if t > 0:
            human_timedelta = f"{t:.0f}{separator}{suffixes[idx]}"
            if t > 1 and style != "new_reddit":
                human_timedelta += "s"
            human_timedelta += " ago"
            break

    return human_timedelta

# Formats `number` to something like '12.2k', '1.1M', etc.
# `style` can be one of ["none", "old_reddit", "new_reddit"]
def number_to_abbreviated_string(number, style):
    if style == "none":
        return number

    abbreviated_str = f"{number:.0f}"
    millions = number / 1000000
    thousands = number / 1000
    if style == "old_reddit":
        suffixes = ["M", "k"]
        thresholds = [1, 10]
    elif style == "new_reddit":
        suffixes = ["M", "K"]
        thresholds = [1, 1]
    counts = [millions, thousands]
    # print(list(zip(suffixes, counts)))
    for idx, n in enumerate(counts):
        frac_part = n - int(n)
        no_decimals = (n < thresholds[idx] and n > 0.9 * thresholds[idx]) or (n >= thresholds[idx] and (frac_part > 0.9 or frac_part < 0.1))
        if style == "new_reddit" and no_decimals:
            abbreviated_str = f"{n:.0f}{suffixes[idx]}"
            break
        elif n >= thresholds[idx]:
            abbreviated_str = f"{n:.1f}{suffixes[idx]}"
            break

    return abbreviated_str
    return abbreviated_str

def set_preferred_theme(theme, page):
    # Alternate method to try to set preferred theme
    preferred_theme = 'dark' if theme == 'dark' else 'light'
    dark_mode_switcher_loc = page.locator('faceplate-switch-input[value="darkmode-switch-value"]').first
    if dark_mode_switcher_loc.count() == 1:
        is_dark_mode_enabled = page.locator('html.theme-dark').first.count() > 0
        if (preferred_theme == "dark" and not is_dark_mode_enabled) or (preferred_theme == "light" and is_dark_mode_enabled):
            print("Try to set theme to " + (preferred_theme) + "...")
            dark_mode_switcher_loc.dispatch_event('click')
            # Ensure to set preferred theme
            page.wait_for_function("""
                preferred_theme => {
                    if (!document.querySelector('html').classList.contains('theme-' + preferred_theme)) {
                        document.querySelector('faceplate-switch-input[value="darkmode-switch-value"]').click();
                    }
                    return true;
                }
            """, arg=preferred_theme)
            # breakpoint()

def bypass_see_this_post_in(page):
    # Bypass "See this post in..."
    see_this_post_in_button = page.locator('#bottom-sheet button.continue').first
    if see_this_post_in_button.is_visible():
        print("See this post in... [CONTINUE]")
        see_this_post_in_button.dispatch_event('click')
        see_this_post_in_button.wait_for(state='hidden')
    else:
        # Ensure to hide backdrop
        backdrop_loc = page.locator('#bottom-sheet #backdrop').first
        if backdrop_loc.count() > 0:
            backdrop_loc.evaluate('node => node.style.display="none"')

def get_comment_excerpt(comment):
    comment_excerpt = (comment["comment_body"].split("\n")[0])
    if len(comment_excerpt) > 80: comment_excerpt = comment_excerpt[:80] + "…"

    return comment_excerpt

def get_screenshots_of_reddit_posts(reddit_object: dict, screenshot_num: int):
    """Downloads screenshots of reddit posts as seen on the web. Downloads to assets/temp/png

    Args:
        reddit_object (Dict): Reddit object received from reddit/subreddit.py
        screenshot_num (int): Number of screenshots to download
    """
    # settings values
    W: Final[int] = int(settings.config["settings"]["resolution_w"])
    H: Final[int] = int(settings.config["settings"]["resolution_h"])
    lang: Final[str] = settings.config["reddit"]["thread"]["post_lang"]
    storymode: Final[bool] = settings.config["settings"]["storymode"]

    print_step("Downloading screenshots of reddit posts...")
    reddit_id = re.sub(r"[^\w\s-]", "", reddit_object["thread_id"])
    # ! Make sure the reddit screenshots folder exists
    assets_temp_folder = Path(f"assets/temp/")
    screenshots_temp_folder = assets_temp_folder / Path(f"{reddit_id}/png")
    screenshots_temp_folder.mkdir(parents=True, exist_ok=True)

    # set the theme and disable non-essential cookies
    if settings.config["settings"]["theme"] == "dark":
        cookie_file = open("./video_creation/data/cookie-dark-mode.json", encoding="utf-8")
        bgcolor = (33, 33, 36, 255)
        txtcolor = (240, 240, 240)
        transparent = False
    elif settings.config["settings"]["theme"] == "transparent":
        if storymode:
            # Transparent theme
            bgcolor = (0, 0, 0, 0)
            txtcolor = (255, 255, 255)
            transparent = True
            cookie_file = open("./video_creation/data/cookie-dark-mode.json", encoding="utf-8")
        else:
            # Switch to dark theme
            cookie_file = open("./video_creation/data/cookie-dark-mode.json", encoding="utf-8")
            bgcolor = (33, 33, 36, 255)
            txtcolor = (240, 240, 240)
            transparent = False
    else:
        cookie_file = open("./video_creation/data/cookie-light-mode.json", encoding="utf-8")
        bgcolor = (255, 255, 255, 255)
        txtcolor = (0, 0, 0)
        transparent = False
    if storymode and settings.config["settings"]["storymodemethod"] == 1:
        # for idx,item in enumerate(reddit_object["thread_post"]):
        print_substep("Generating images...")
        return imagemaker(
            theme=bgcolor,
            reddit_obj=reddit_object,
            txtclr=txtcolor,
            transparent=transparent,
        )

    with sync_playwright() as p:
        headless_browser = settings.config["settings"]["headless_browser"]
        print_substep("Launching " + ("Headless " if headless_browser else "") + "Browser...")

        browser = p.chromium.launch(
            headless=headless_browser
        )  # headless=False will show the browser for debugging purposes
        # Device scale factor (or dsf for short) allows us to increase the resolution of the screenshots
        # When the dsf is 1, the width of the screenshot is 600 pixels
        # so we need a dsf such that the width of the screenshot is greater than the final resolution of the video
        dsf = (W // 600) + 1

        # User Agent
        ua = "Mozilla/5.0 (Linux; Android 8.0.0; MI 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.101 Mobile Safari/537.36"

        context = browser.new_context(
            locale=lang or "en-us",
            color_scheme="dark",
            viewport=ViewportSize(width=W, height=H),
            device_scale_factor=dsf,
            user_agent=ua,
        )

        cookies = json.load(cookie_file)
        cookie_file.close()

        context.add_cookies(cookies)  # load preference cookies

        page = context.new_page()

        screenshot_debug = settings.config["settings"]["screenshot_debug"]

        # Login to Reddit
        print_substep("[BROWSER] Logging into Reddit...")

        # Use old.reddit.com to login only (go to reddit.com for actual posts/comments later)
        page.goto("https://old.reddit.com/login", timeout=0)
        # page.set_viewport_size(ViewportSize(width=1920, height=1080))
        page.set_viewport_size(ViewportSize(width=1200, height=720))
        login_url = page.url

        username_loc = page.locator("#login-form #user_login").first
        password_loc = page.locator("#login-form #passwd_login").first
        button_loc = page.locator("#login-form button[type='submit']").first

        print("Logging in via old.reddit.com/login...")
        username_loc.fill(settings.config["reddit"]["creds"]["username"])
        password_loc.fill(settings.config["reddit"]["creds"]["password"])
        button_loc.first.click()

        # Check for login error message
        login_error_loc = page.locator("#login-form .c-form-control-feedback-error").first
        if login_error_loc.is_visible():
            print_substep(
                "Login unsuccessful: probably your reddit credentials are incorrect! Please modify them accordingly in the config.toml file.",
                style="red",
            )
            exit()

        # Wait for navigation to page different from the login one
        not_login_url_regex = re.compile('^(?!' + login_url + ')')
        page.wait_for_url(not_login_url_regex, wait_until="commit") # wait_until='commit' -> wait until another url started loading

        current_url = page.url
        if current_url == "https://old.reddit.com/":
            print("Login successful!")
        else:
            print_substep(
                "Login unsuccessful: probably your reddit credentials are incorrect! Please modify them accordingly in the config.toml file.",
                style="red",
            )
            exit()

        # Goto thread url
        page.goto(reddit_object["thread_url"], timeout=0)
        page.set_viewport_size(ViewportSize(width=W, height=H))
        page.set_viewport_size(ViewportSize(width=1200, height=720))
        page.wait_for_load_state()
        page.wait_for_timeout(5000)

        # Try to set preferred theme from settings
        set_preferred_theme(settings.config["settings"]["theme"], page)

        # Bypass "See this post in..."
        bypass_see_this_post_in(page)

        if page.locator(
            "#t3_12hmbug > div > div._3xX726aBn29LDbsDtzr_6E._1Ap4F5maDtT1E1YuCiaO0r.D3IL3FD0RFy_mkKLPwL4 > div > div > button"
        ).is_visible():
            # This means the post is NSFW and requires to click the proceed button.

            print_substep("Post is NSFW. You are spicy...")
            page.locator(
                "#t3_12hmbug > div > div._3xX726aBn29LDbsDtzr_6E._1Ap4F5maDtT1E1YuCiaO0r.D3IL3FD0RFy_mkKLPwL4 > div > div > button"
            ).click()
            page.wait_for_load_state()  # Wait for page to fully load

        if page.locator(
            "#SHORTCUT_FOCUSABLE_DIV > div:nth-child(7) > div > div > div > header > div > div._1m0iFpls1wkPZJVo38-LSh > button > i"
        ).is_visible():
            page.locator(
                "#SHORTCUT_FOCUSABLE_DIV > div:nth-child(7) > div > div > div > header > div > div._1m0iFpls1wkPZJVo38-LSh > button > i"
            ).click()  # Interest popup is showing, this code will close it

        if lang:
            # translate code
            print_substep("Translating post...")
            texts_in_tl = translators.translate_text(
                reddit_object["thread_title"],
                to_language=lang,
                translator="google",
            )

            page.evaluate(
                "tl_content => document.querySelector('h1[id^=\"post-title\"]').textContent = tl_content",
                texts_in_tl,
            )
        else:
            print_substep("Skipping translation...")

        postcontentpath = f"assets/temp/{reddit_id}/png/title.png"
        try:
            post_loc = page.locator("shreddit-post")

            # Bypass "See this post in..."
            bypass_see_this_post_in(page)

            if settings.config["settings"]["zoom"] != 1:
                # store zoom settings
                zoom = settings.config["settings"]["zoom"]
                # zoom the body of the page
                page.evaluate("document.body.style.zoom=" + str(zoom))
                # as zooming the body doesn't change the properties of the divs, we need to adjust for the zoom
                post_loc = post_loc.bounding_box()
                for i in post_loc:
                    post_loc[i] = float("{:.2f}".format(post_loc[i] * zoom))
                page.screenshot(clip=post_loc, path=postcontentpath)
            else:
                post_loc.first.screenshot(path=postcontentpath)
        except Exception as e:
            print_substep("Something went wrong!", style="red")
            resp = input(
                "Something went wrong with making the screenshots! Do you want to skip the post? (y/n) "
            )

            if resp.casefold().startswith("y"):
                save_data("", "", "skipped", reddit_id, "")
                print_substep(
                    "The post is successfully skipped! You can now restart the program and this post will skipped.",
                    "green",
                )

            resp = input("Do you want the error traceback for debugging purposes? (y/n)")
            if not resp.casefold().startswith("y"):
                exit()

            raise e

        if storymode:
            page.locator('[data-click-id="text"]').first.screenshot(
                path=f"assets/temp/{reddit_id}/png/story_content.png"
            )
        else:
            use_template = settings.config["settings"]["use_template"]
            if use_template:
                template_url = str(Path("comment_templates", settings.config["settings"]["template_url"]))
                # Read the Jinja template from a file
                print(f"Using Comment Template : {template_url}")
                template_abbreviated_style = settings.config["settings"]["template_abbreviated_style"]
                if not (template_abbreviated_style in ["none", "old_reddit", "new_reddit"]):
                    template_abbreviated_style = "none"
                print(f"Template Abbr. Style   : {template_abbreviated_style}")

                # Create a Jinja environment with UTF-8 encoding
                env = Environment(loader=FileSystemLoader(template_url))
                # Load the template
                template = env.get_template('index.html')
            
            accepted_comments = reddit_object["comments"][:screenshot_num]
            for idx, comment in enumerate(
                accepted_comments if screenshot_debug else track(accepted_comments, "Downloading screenshots...")
            ):
                # Stop if we have reached the screenshot_num
                if idx >= screenshot_num:
                    break

                comment_path: Path = screenshots_temp_folder / Path(f"comment_{idx}.png")
                    
                comment_obj = comment["obj"]

                if comment_path.exists():
                    print(f"Comment Screenshot already downloaded : {comment_path}")
                else:
                    if screenshot_debug:
                        comment_excerpt = get_comment_excerpt(comment)
                        print(f"[{idx + 1}/{screenshot_num} {comment['comment_id']}]: {comment_excerpt}")

                    if use_template:

                        # translate code
                        if settings.config["reddit"]["thread"]["post_lang"]:
                            comment_tl = translators.translate_html(
                                comment_obj.body_html,
                                to_language=lang,
                                translator="google",
                            )
                            comment_obj.body_html = comment_tl
                        
                        # Fill template fields and update page
                        values = {
                            'author': comment_obj.author.name if comment_obj.author else '[unknown]',
                            'id': comment_obj.id,
                            'score': number_to_abbreviated_string(comment_obj.score, style=template_abbreviated_style),
                            'avatar': comment_obj.author.icon_img if comment_obj.author else '[unknown]',
                            'date': datetime_to_human_timedelta(dt.datetime.fromtimestamp(comment_obj.created), style=template_abbreviated_style),
                            'body_text': comment_obj.body,
                            'body_html': comment_obj.body_html,
                        }
                        # Render the template with variables
                        output = template.render(values)

                        # Save the rendered output to a file
                        if settings.config["settings"]["template_debug"]:
                            template_output_file = f"{screenshots_temp_folder}/comment_{idx}.html"
                            print(f"Jinja Comment Output : '{template_output_file}'")
                            # print(output)
                            with open(template_output_file, "w", encoding="utf-8") as output_file:
                                output_file.write(output)

                        # Option 1: Pass HTML content
                        page.set_content(output)

                        page.locator('#comment-container').screenshot(path=str(comment_path.resolve()))

                    else:

                        if page.locator('[data-testid="content-gate"]').is_visible():
                            page.locator('[data-testid="content-gate"] button').click()

                        page.goto(f'https://reddit.com{comment["comment_url"]}', timeout=0)

                        # Try to set preferred theme from settings
                        set_preferred_theme(settings.config["settings"]["theme"], page)

                        # translate code
                        if settings.config["reddit"]["thread"]["post_lang"]:
                            comment_tl = translators.translate_text(
                                comment["comment_body"],
                                to_language=lang,
                                translator="google",
                            )
                            page.evaluate(
                                '([tl_content, tl_id]) => document.querySelector(`#t1_${tl_id} > div:nth-child(2) > div > div[data-testid="comment"] > div`).textContent = tl_content',
                                [comment_tl, comment["comment_id"]],
                            )
                            
                        try:
                            comment_selector = f'shreddit-comment[thingid="t1_{comment["comment_id"]}"]'
                            comment_loc = page.locator(comment_selector)
                            if settings.config["settings"]["zoom"] != 1:
                                # store zoom settings
                                zoom = settings.config["settings"]["zoom"]
                                # zoom the body of the page
                                page.evaluate("document.body.style.zoom=" + str(zoom))
                                # scroll comment into view
                                comment_loc.scroll_into_view_if_needed()
                                # as zooming the body doesn't change the properties of the divs, we need to adjust for the zoom
                                comment_loc.bounding_box()
                                for i in location:
                                    location[i] = float("{:.2f}".format(location[i] * zoom))
                                page.screenshot(
                                    clip=comment_loc,
                                    path=f"assets/temp/{reddit_id}/png/comment_{idx}.png",
                                )
                            else:
                                # Bypass "See this post in..."
                                bypass_see_this_post_in(page)

                                # Click on "View more comments", if present
                                view_more_comments_button = page.locator('.overflow-actions-dialog ~ button').first
                                if view_more_comments_button.is_visible():
                                    print("View more comments... [CLICK]")
                                    view_more_comments_button.dispatch_event('click')
                                    view_more_comments_button.wait_for(state='hidden')

                                # If the comment text itself is collapsed, expand it
                                comment_text_loc = comment_loc.locator("p").first
                                if not comment_text_loc.is_visible():
                                    self_expand_button_loc = comment_loc.locator('summary button').first
                                    if self_expand_button_loc.is_visible():
                                        self_expand_button_loc.dispatch_event('click')

                                # If replies are expanded toggle them
                                expanded_loc = comment_loc.locator('button[aria-expanded="true"]').first
                                if expanded_loc.is_visible():
                                    #print("If replies are expanded toggle them")
                                    expanded_loc.dispatch_event("click")

                                # breakpoint()
                                comment_loc.first.screenshot(
                                    path=f"assets/temp/{reddit_id}/png/comment_{idx}.png"
                                )
                        except TimeoutError:
                            del reddit_object["comments"]
                            screenshot_num += 1
                            print("TimeoutError: Skipping screenshot...")
                            continue

        # close browser instance when we are done using it
        browser.close()

    print_substep("Screenshots downloaded Successfully.", style="bold green")
