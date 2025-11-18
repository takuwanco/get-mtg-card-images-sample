from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time
import re
import requests
from PIL import Image
from io import BytesIO
import os
import glob
import configparser
import ast


# INIファイルの読み込み
config = configparser.ConfigParser()
config.read('config.ini')

# selenium用のChromeDriver
WEB_DRIVER_PATH = config.get('Paths', 'WEB_DRIVER_PATH')

# 変換後の画像の情報
STR_PNG = "PNG"
IMAGE_EXT = ".png"

# 画像保存先
SAVE_FOLDER_FRONT = config.get('Paths', 'SAVE_FOLDER_FRONT')  # "img_front"
SAVE_FOLDER_BACK  = config.get('Paths', 'SAVE_FOLDER_BACK')   # "img_back"
SAVE_FOLDER_BASIC = config.get('Paths', 'SAVE_FOLDER_BASIC')  # "img_basic"

# 英日カード名対応表
EN_JA_NAME_LIST = config.get('Paths', 'EN_JA_NAME_LIST')    # "en_ja_name_list.txt"

# 各種URL
SET_TYPE = config.get('URL', 'SET_TYPE')                  # 例: "mtgarena"
SET_NAME = config.get('URL', 'SET_NAME')                  # 例: "through-the-omenpaths"
CIGPRODUCT = config.get('URL', 'CIGPRODUCT')              # 例: "om1-products-arena-limited-pack"
CIGSET = ast.literal_eval(config.get('URL', 'CIGSET'))    # 例: ['OM1', 'OMB'] を配列化
JA_URL = "https://magic.wizards.com/ja/" + SET_TYPE + "/" + SET_NAME + "/card-image-gallery?cigproduct=" + CIGPRODUCT
EN_URL = JA_URL.replace("https://magic.wizards.com/ja/", "https://magic.wizards.com/en/")
PLAY_BOOSTER = config.get('URL', 'PLAY_BOOSTER')          # 例: "tla-products-play-boosters"
LAND_URL = "https://magic.wizards.com/ja/" + SET_TYPE + "/" + SET_NAME + "/card-image-gallery?cigproduct=" + PLAY_BOOSTER + "&cigsubtype=plains&cigsubtype=forest&cigsubtype=mountain&cigsubtype=island&cigsubtype=swamp"

# Selenium設定
SCROLL_PAUSE_TIME = config.getint('Selenium', 'SCROLL_PAUSE_TIME')   # 1     # スクロール後の待機時間（調整可能）
SCROLL_AMOUNT     = config.getint('Selenium', 'SCROLL_AMOUNT')       # 500   # 一回のスクロール量（ピクセル）


# 初期化
def _init():
    # 英日カード名対応表の初期化
    if os.path.isfile(EN_JA_NAME_LIST):
        os.remove(EN_JA_NAME_LIST)

    # 画像保存先の初期化
    dir_list = [SAVE_FOLDER_FRONT, SAVE_FOLDER_BACK, SAVE_FOLDER_BASIC]
    for dir in dir_list:
        os.makedirs(dir, exist_ok=True)
        png_files = glob.glob(os.path.join(dir, "*" + IMAGE_EXT))
        for file in png_files:
            os.remove(file)


# ファイルパス取得用
def getCardImageFilePath(filename, folder=SAVE_FOLDER_FRONT):
    return os.path.join(folder, filename)


# ファイルの存在チェック
def existsCardImageFile(filename, folder=SAVE_FOLDER_FRONT):
    path = getCardImageFilePath(filename, folder)
    return os.path.isfile(path)


# 用意したファイル名が既に存在するファイル名の場合、カウントアップして、重複しないファイル名を用意する
def getFilenameWithoutDuplication(CARD_NAME, folder=SAVE_FOLDER_FRONT):
    filename = CARD_NAME + IMAGE_EXT

    if existsCardImageFile(filename, folder):
        counter = 1
        filename = CARD_NAME + "_" + str(counter) + IMAGE_EXT
        while existsCardImageFile(filename, folder):
            counter = counter + 1
            filename = CARD_NAME + "_" + str(counter) + IMAGE_EXT

    return filename


###################################################################
# lazyload対応で、SeleniumでカードギャラリーのURLからカード情報を取得 
###################################################################
def getCardList(url):
    # Chrome WebDriverの設定
    chrome_options = Options()
    service = Service(WEB_DRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    print("target url : " + url)

    # 指定されたWebページを開く
    driver.maximize_window()
    driver.get(url)

    # ページが完全に読み込まれるのを待つ（必要に応じて調整）
    driver.implicitly_wait(5)

    # ページを少しずつスクロール
    last_scrollTop      = -1
    last_scrollHeight   = -1

    while True:
        driver.execute_script(f"window.scrollBy(0, {SCROLL_AMOUNT});")
        time.sleep(SCROLL_PAUSE_TIME)
        
        # スクロール後のページの高さを取得
        scrollTop = driver.execute_script("return document.documentElement.scrollTop")
        scrollHeight = driver.execute_script("return document.documentElement.scrollHeight")
        print("scrollTop is ", scrollTop, ". scrollHeight is ", scrollHeight)

        # スクロール位置とページの高さが変わらなければ終了
        if scrollTop == last_scrollTop and scrollHeight == last_scrollHeight:
            break

        last_scrollTop      = scrollTop
        last_scrollHeight   = scrollHeight

    # 最終的なHTMLを取得
    html = driver.page_source

    driver.quit()

    # BeautifulSoupでHTMLを解析
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.find_all("magic-card")

    # 日英共通のカードキー抽出用パターン
    CARD_PATTERN = r"https://media\.wizards\.com/(.+)/(.+)/(.+)/(.+\.webp)"

    # データをリストに格納
    data = []
    for card in cards:
        name = card.get("name", "")
        face = card.get("face", "")
        back = card.get("back", "")

        # 正規表現で抽出
        match = re.search(CARD_PATTERN, face)
        set = ""
        key = ""
        if match:
            year    = match.group(1) 
            set     = match.group(2)
            key     = match.group(3)
            filename = match.group(4)
        else:
            pass

        data.append({"name": name, "face": face, "back": back, "set": set, "key": key})
    
    return data


###########################################
# webp画像URLからPNG画像を指定フォルダに保存
###########################################
def saveImage(filename, webp_url, folder=SAVE_FOLDER_FRONT):
    # WebP画像をダウンロード
    response = requests.get(webp_url)
    if response.status_code == 200:
        webp_image = Image.open(BytesIO(response.content))
        
        # PNGに変換して保存
        path = getCardImageFilePath(filename, folder)
        webp_image.save(path, STR_PNG)
    else:
        print("Saving Image Failed : " + filename)
    return


##########
# main
##########
if __name__ == "__main__":
    _init()

    # 英日カード名の対応表
    en_ja_name_list = []
    
    for cigset in CIGSET:

        # カードギャラリー情報の取得
        ja_data = getCardList(JA_URL + "&cigset=" + cigset)
        en_data = getCardList(EN_URL + "&cigset=" + cigset)


        for ja_card in ja_data:
            # 日本語カード名と画像URLの取得
            ja_card_name = ja_card["name"]
            ja_card_url = ja_card["face"]
            ja_card_url_back = ja_card["back"]

            # 画像ファイル名の決定
            filename = getFilenameWithoutDuplication(ja_card_name)

            # 画像の保存
            saveImage(filename, ja_card_url)
            if ja_card_url_back != "":
                # 裏面画像がある場合は裏面画像用のフォルダに保存
                back_filename = getFilenameWithoutDuplication(ja_card_name + "_back")
                saveImage(back_filename, ja_card_url_back, folder=SAVE_FOLDER_BACK)

            # 英日カード名の取得
            EN_SAME_CARD_URL = ja_card_url.replace("/jp_", "/en_")
            for en_card in en_data:
                # 英語カード名と画像URLの取得
                en_card_name = en_card["name"]
                en_card_url = en_card["face"]

                # 画像URLが「jp_」「en_」を除いて同じなら、英日カード名の対応表に登録
                if en_card_url == EN_SAME_CARD_URL:
                    print(en_card_name, ja_card_name)
                    en_ja_name_list.append({"en_name": en_card_name, "ja_name": ja_card_name})
                    break

    # 英日カード名の対応表を保存
    with open(EN_JA_NAME_LIST, "a", encoding="utf-8") as f:
        for item in en_ja_name_list:
            f.write(f"{item['en_name']}\t{item['ja_name']}\n")

    # 基本土地 (違うのが入ってくることもある。重複することもある)
    land_data = getCardList(LAND_URL)
    for card in land_data:
        card_name = card["name"]
        filename = getFilenameWithoutDuplication(card_name, folder=SAVE_FOLDER_BASIC)
        card_url = card["face"]
        saveImage(filename, card_url, folder=SAVE_FOLDER_BASIC)
            
