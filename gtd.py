import os
import re
from dataclasses import dataclass
from os import path
from typing import List, Iterator, Optional

import requests
import toml
from bs4 import BeautifulSoup, NavigableString, Tag, PageElement


def login(user: str, password: str) -> requests.Session:
    sess = requests.Session()

    login_page = "https://www.guitartricks.com/process/loginAjax"

    sess.post(login_page, {
        "action": "verify_login",
        "login": user,
        "password": password
    })

    return sess


# ---------------------------------------------------------
# Get lessons
# ---------------------------------------------------------


@dataclass
class Lesson:
    chapter: Optional[str]
    tutorial: Optional[str]
    tutorial_number: int
    lesson: str
    lesson_url: str
    lesson_number: int


def get_lessons_from_lesson_list(chapter: Optional[str], tutorial: Optional[str], tutorial_number: int, lesson_list: Tag) -> Iterator[Lesson]:
    lesson_number = 0
    for item in lesson_list:
        if isinstance(item, Tag) and "course__lessonTitle" in item["class"]:
            lesson = item["title"]
            lesson_url = item.find("a")["href"]
            lesson_number += 1
            yield Lesson(
                chapter=chapter,
                tutorial=tutorial, tutorial_number=tutorial_number,
                lesson=lesson, lesson_url=lesson_url, lesson_number=lesson_number
            )
        elif isinstance(item, NavigableString):
            continue
        else:
            raise Exception(f"Unknown item in lesson list: {item}")


def get_lessons_from_tutorial_list(chapter: Optional[str], tutorial_list: Tag) -> Iterator[Lesson]:
    tutorial = None
    tutorial_number = 0
    for item in tutorial_list:
        if isinstance(item, Tag) and "course__tutorialTitle" in item["class"]:
            tutorial = item.text.strip()
            tutorial_number += 1
        elif isinstance(item, Tag) and "course__lessonList" in item["class"]:
            yield from get_lessons_from_lesson_list(chapter, tutorial, tutorial_number, item)
        elif isinstance(item, NavigableString):
            continue
        else:
            raise Exception(f"Unknown item in tutorial list: {item}")


def get_lessons_from_chapter_list(chapter_list: Iterator[PageElement]) -> Iterator[Lesson]:
    chapter = None
    for item in chapter_list:
        if isinstance(item, Tag) and "course__chapterTitle" in item["class"]:
            chapter = item.find("div", {"class": "course__chapterTitle__inner"})["title"]
        elif isinstance(item, Tag) and "course__tutorialList" in item["class"]:
            yield from get_lessons_from_tutorial_list(chapter, item)
        elif isinstance(item, NavigableString):
            continue
        else:
            raise Exception(f"Unknown item in chapter list: {item}")


def get_lessons(sess: requests.Session, course_url: str) -> List[Lesson]:
    soup = BeautifulSoup(sess.get(course_url).text, features="html.parser")
    chapter_list = soup.find("div", {"class": "course__chapterList"}).children
    return list(get_lessons_from_chapter_list(chapter_list))


# ---------------------------------------------------------
# Download lessons
# ---------------------------------------------------------


def to_abs_url(rel_url):
    return "https://www.guitartricks.com" + rel_url


def download_file(sess, url, local_file):
    tmp_file = local_file + ".part"
    with sess.get(url, stream=True) as r:
        with open(tmp_file, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    os.rename(tmp_file, local_file)


def sanitize(name):
    replaced_colon = re.sub("\\b: ", " - ", name)
    replaced_ampersand = re.sub(" & ", " and ", replaced_colon)
    replaced_slash_in_fraction = re.sub("(\\d)/(\\d)", "\\1 over \\2", replaced_ampersand)
    removed_special_chars = re.sub("[?!'.]", "", replaced_slash_in_fraction)

    result = removed_special_chars

    if not re.fullmatch("[a-zA-Z0-9-, ()#]+", result):
        raise Exception(f"Not sanitized properly '{result}'.")
    else:
        return result


def download_lesson_video(sess, lesson, file):
    soup = BeautifulSoup(sess.get(to_abs_url(lesson.lesson_url)).text, features="html.parser")
    download_button = next(
        b for b in soup.find_all("button", {"class": "lessonButton"})
        if b.text.strip() == "DOWNLOAD LESSON"
    )

    # Extract URL from onclick attribute which looks like
    # onclick="window.open('/downloadgenerator.php?input=21986')"
    onclick = download_button["onclick"]
    download_page_url = re.search("open\\('(.*?)'\\)", onclick).group(1)

    # Get download page and extract video URL.
    soup = BeautifulSoup(sess.get(to_abs_url(download_page_url)).text, features="html.parser")
    content_section = soup.find("section", {"id": "content"})

    if content_section is None:
        msg = soup.text.strip()
        raise Exception(f"Cannot download video for {lesson}.\nMessage: {msg}")

    links = content_section.find_all("a")
    if len(links) > 1:
        raise Exception("More video download links!")
    else:
        link = links[0]
    video_url = link["href"]

    download_file(sess, video_url, file)


def download_guitar_notation(sess, lesson, file):
    soup = BeautifulSoup(sess.get(to_abs_url(lesson.lesson_url)).text, features="html.parser")
    print_buttons = [
        b for b in soup.find_all("button", {"class": "lessonButton"})
        if b.text.strip() == "PRINT NOTATION"
    ]

    if len(print_buttons) == 0:
        print("No notation found.")
        return
    elif len(print_buttons) > 1:
        raise Exception(f"Multiple buttons for downloading notation found: {print_buttons}")

    print_button = print_buttons[0]

    # Extract URL from onclick attribute which looks like
    # onclick="window.open('/lessonpdf3.php?trick_id=22361','Lesson Print Window',
    onclick = print_button["onclick"]
    pdf_url = re.search("open\\('(.*?)',", onclick).group(1)

    download_file(sess, to_abs_url(pdf_url), file)


def download_lesson(sess, lesson, basedir="."):
    dir = path.join(
        basedir,
        sanitize(lesson.chapter),
        sanitize(f"{lesson.tutorial_number:02} - {lesson.tutorial}")
    )
    os.makedirs(dir, exist_ok=True)

    file = sanitize(f"{lesson.lesson_number:02} - {lesson.lesson}")

    video_file = path.join(dir, f"{file}.mp4")
    if not path.exists(video_file):
        print(f"Downloading video {video_file}.")
        download_lesson_video(sess, lesson, video_file)

        download_notation = True
    else:
        print(f"Skipping already existing {video_file}.")

        download_notation = False

    notation_file = path.join(dir, f"{file}.pdf")
    if not path.exists(notation_file) and download_notation:
        print(f"Downloading notation {notation_file}.")
        download_guitar_notation(sess, lesson, notation_file)
    else:
        print(f"Skipping already existing {notation_file}.")


# ---------------------------------------------------------
# Main code
# ---------------------------------------------------------


config = toml.load("config.toml")

user = config["user"]
password = config["password"]
sess = login(user, password)

course_url = config["course-url"]
lessons = get_lessons(sess, course_url)

basedir = config["basedir"]
for lesson in lessons:
    download_lesson(sess, lesson, basedir)
