import scrapy
from scrapy import Selector
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
# from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
import logging
from datetime import datetime
from ..items import ArticleItem
from ..utils import utils
import time

root = 'https://www.der-postillon.com/p/das-postillon-archiv.html'
# short_url_regex = "!\d{5,}"         # helps converting long to short url: https://www.der-postillon.com/!2345678/

testrun_cats = 0                    # limits the categories to crawl to this number. if zero, no limit.
testrun_arts = 0                    # limits the article links to crawl to this number. if zero, no limit.
                                    # For deployment: don't forget to set the testrun variables to zero


# options = Options()
# options.BinaryLocation = "/usr/bin/chromium-browser"

# driver = webdriver.Chrome(executable_path="/usr/bin/chromedriver",options=options)
# driver.get(root)


# alternative setup with headless chrome: https://medium.com/@pyzzled/running-headless-chrome-with-selenium-in-python-3f42d1f5ff1d
# WebDriverWait see https://stackoverflow.com/questions/53134306/deprecationwarning-use-setter-for-headless-property-instead-of-set-headless-opt
# try:
#     firefoxOptions = webdriver.FirefoxOptions()
#     # firefoxOptions.set_headless() # deprecated
#     firefoxOptions.headless = True
#     browser = webdriver.Firefox(firefox_options=firefoxOptions)
#     print(firefoxOptions.headless)
#     print(browser)
#     browser.get('https://www.der-postillon.com/p/das-postillon-archiv.html')
#     # print(browser.page_source)
# finally:
#     try:
#         browser.close()
#     except:
#         pass



class PostillonSpider(scrapy.Spider):
    name = "postillon"
    start_url = root
    
    # TODO: decide whether to move this code into parse function and close driver at end of parsing
    # def __init__(self):
        # # self.driver = webdriver.Firefox()
        # firefoxOptions = webdriver.FirefoxOptions()
        # # firefoxOptions.set_headless() # deprecated
        # # options.add_argument("headless")
        # firefoxOptions.headless = True
        # # self.driver = webdriver.Firefox(firefox_options=firefoxOptions)
        # desired_capabilities = firefoxOptions.to_capabilities()
        # driver = webdriver.Firefox(desired_capabilities=desired_capabilities)
        # driver.get(root)
        
        # # Wait
        # driver.implicitly_wait(10)
        # # wait = WebDriverWait(driver, 5)
        # # wait.unitl(EC.presence_of_element_located((By.CLASS_NAME, "month-inner")))
        # time.sleep(2)
        
        # months = driver.find_elements_by_class_name("month-inner")

    
    # TODO: finally: driver.quit()
    def start_requests(self):
        yield scrapy.Request(self.start_url, callback=self.parse)

    
    def parse(self, response):
        def init_selenium_driver():
            firefoxOptions = webdriver.FirefoxOptions()
            firefoxOptions.headless = True
            # self.driver = webdriver.Firefox(firefox_options=firefoxOptions) # TODO: check whether it is preferred to use desired_capabilities or firefox_options
            desired_capabilities = firefoxOptions.to_capabilities()
            driver = webdriver.Firefox(desired_capabilities=desired_capabilities)
            return driver

        driver = init_selenium_driver()

        driver.get(root)
        elements = driver.find_elements_by_class_name('closed') # also finds closed months inside closed years
        
        # elements = elements[:10] # TODO: remove / apply crawl limit
        for element in elements:
            try:
                driver.execute_script("arguments[0].click();", element) # element.click() causes Exception: "could not be scrolled into view"
            except Exception as e:
                print(e)


        # Hand-off between Selenium and Scrapy
        sel = Selector(text=driver.page_source)
        linklist = sel.xpath('//ul[@class="month-inner"]//li/a/@href').extract()

        # linklist = utils.limit_crawl(linklist,testrun_arts)  # TODO apply crawl limit
        if linklist:
            for long_url in linklist:
                print(long_url)
                # if short_url and not utils.is_url_in_db(short_url):  # db-query
                # if not utils.is_url_in_db(long_url):  # db-query TODO: use, when db properly connected
                if True:
                    print("url not in db")
                    # yield scrapy.Request(short_url+"/", callback=self.parse_article,
                    #                      cb_kwargs=dict(short_url=short_url, long_url=long_url))
                    # yield scrapy.Request(long_url, callback=self.parse_article)

                else:
                    print("url in db")
                    # utils.log_event(utils(), self.name, short_url, 'exists', 'info')
                    # logging.info('%s already in db', short_url)
                    utils.log_event(utils(), self.name, long_url, 'exists', 'info')
                    logging.info('%s already in db', long_url)

        driver.quit()


    def parse_article(self, response, short_url, long_url):
        print("entered parse_article")
        print(long_url)
        utils_obj = utils()

        def get_article_text():
            article_paragraphs = []
            html_article = response.xpath('//article/*').extract()      # every tag in <article>
            for tag in html_article:
                line = ""
                # only p tags with 'xmlns="" and class beginning with "article..." (=paragraphs)
                # or h6-tags (=subheadings)
                if "p xmlns=\"\" class=\"article" in tag or tag[2]=="6":
                    tag_selector = Selector(text=tag)
                    html_line = tag_selector.xpath('//*/text()').extract()
                    for text in html_line:
                        line+=text
                    article_paragraphs.append(line)
            article_text = ""
            for paragraph in article_paragraphs:
                if paragraph:
                    article_text += paragraph + "\n\n"
            text = article_text.strip()
            if not text:
                utils.log_event(utils_obj, self.name, short_url, 'text', 'warning')
                logging.warning("Cannot parse article text: %s", short_url)
            return text


        # if published_time is not set or wrong format, try modified, then None
        def get_pub_time():
            def parse_pub_time(time_str):
                try:
                    return datetime.strptime(time_str,'%Y-%m-%dT%H:%M:%S%z')  # "2019-11-14T10:50:00+01:00"
                except:
                    time_str = time_str[:-6]
                    try:
                        return datetime.strptime(time_str, '%Y-%m-%dT%H:%M:%S')  # "2019-11-14T10:50:00"
                    except:
                        return None

            published_time_string = response.xpath('//meta[@property="article:published_time"]/@content').get()
            modified_time_string = response.xpath('//meta[@property="article:modified_time"]/@content').get()
            pub_time = parse_pub_time(published_time_string)
            mod_time = parse_pub_time(modified_time_string)
            if pub_time is not None:
                return pub_time
            elif mod_time is not None:
                return mod_time
            else:
                utils.log_event(utils_obj, self.name, short_url, 'published_time', 'warning')
                logging.warning("Cannot parse published time: %s", short_url)
                return None



        # Preparing for Output -> see items.py
        item = ArticleItem()

        item['crawl_time'] = datetime.now()
        item['long_url'] = utils.add_host_to_url(utils_obj, long_url, root)
        item['short_url'] = short_url

        item['news_site'] = "taz"
        item['title'] = utils.get_item_string(utils_obj, response, 'title', short_url, 'xpath',
                                              ['//meta[@property="og:title"]/@content'], self.name)
        item['authors'] = utils.get_item_list(utils_obj, response, 'authors', short_url, 'xpath',
                                              ['//meta[@name="author"]/@content'], self.name)
        item['description'] = utils.get_item_string(utils_obj, response, 'description', short_url, 'xpath',
                                                    ['//meta[@name="description"]/@content'], self.name)
        item['intro'] = utils.get_item_string(utils_obj, response, 'intro', short_url, 'xpath',
                                              ['//article/p[@class="intro "]/text()'], self.name)
        item['text'] = get_article_text()

        keywords = utils.get_item_list_from_str(utils_obj, response, 'keywords', short_url, 'xpath',
                                                ['//meta[@name="keywords"]/@content'],', ', self.name)
        item['keywords'] = list(set(keywords) - {"taz", "tageszeitung "})
        item['published_time'] = get_pub_time()

        image_links = utils.get_item_list(utils_obj, response, 'image_links', short_url, 'xpath',
                                          ['//meta[@property="og:image"]/@content'], self.name)
        item['image_links'] = utils.add_host_to_url_list(utils_obj, image_links, root)

        links = utils.get_item_list(utils_obj, response, 'links', short_url, 'xpath',
                                    ['//article /p[@xmlns=""]/a/@href'], self.name)
        item['links'] = utils.add_host_to_url_list(utils_obj, links, root)

        # don't save article without title or text
        if item['title'] and item['text']:
            yield item
        else:
            logging.info("Cannot parse article: %s", short_url)
            utils.log_event(utils_obj, self.name, short_url, 'missingImportantProperty', 'info')

