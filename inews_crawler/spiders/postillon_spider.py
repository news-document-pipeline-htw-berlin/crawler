import scrapy
from scrapy import Selector
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import logging
from datetime import datetime
from ..items import ArticleItem
from ..utils import utils
import time
import re

root = 'https://www.der-postillon.com/p/das-postillon-archiv.html'

# limits the categories to crawl to this number. if zero, no limit.
testrun_cats = 0
# limits the number of closed year- and month-archive-entities to open (and reveal contained months/articles)
testrun_years_and_months = 1
# limits the article links to crawl to this number. if zero, no limit.
testrun_articles = 1
# For deployment: don't forget to set the testrun variables to zero
# 'https://www.der-postillon.com/2020/11/sonntagsfrage-nerze.html'  # Only scrape the specified article
testrun_article_url = 'https://www.der-postillon.com/2020/11/agent-smith.html'


class PostillonSpider(scrapy.Spider):
    name = "postillon"
    start_url = root

    def start_requests(self):
        if testrun_article_url:
            yield scrapy.Request(testrun_article_url, callback=self.parse_article,  cb_kwargs=dict(long_url=testrun_article_url, published_time="13.11.2020"))
        else:
            yield scrapy.Request(self.start_url, callback=self.parse)

    # Scrape archive for articles
    def parse(self, response):
        def init_selenium_driver():
            firefoxOptions = webdriver.FirefoxOptions()
            firefoxOptions.headless = True
            desired_capabilities = firefoxOptions.to_capabilities()
            driver = webdriver.Firefox(
                desired_capabilities=desired_capabilities)
            return driver

        driver = init_selenium_driver()

        driver.get(root)
        # also finds closed months inside closed years
        elements = driver.find_elements_by_class_name('closed')

        elements = elements[:testrun_years_and_months]  # crawl limit
        for element in elements:
            try:
                # element.click() causes Exception: "could not be scrolled into view"
                driver.execute_script("arguments[0].click();", element)
            except Exception as e:
                print(e)

        # Hand-off between Selenium and Scrapy
        sel = Selector(text=driver.page_source)
        # linklist = sel.xpath('//ul[@class="month-inner"]//li/a/@href').extract()
        articleList = sel.xpath('//ul[@class="month-inner"]//li/a')

        # TODO apply crawl limit also for Selenium link crawling
        articleList = utils.limit_crawl(articleList, testrun_articles)

        if articleList:
            for article in articleList:
                long_url = article.xpath('./@href').extract()[0]
                # TODO: check if list is empty
                # long_url = article.xpath('./@href').extract()
                # long_url = long_url[0] if long_url != [] else ''
                published_time = article.xpath(
                    './/div[@class="date"]/text()').extract()
                published_time = published_time[0] if len(
                    published_time) > 0 else ''

                # print(long_url)
                # if short_url and not utils.is_url_in_db(short_url):  # db-query
                # if not utils.is_url_in_db(long_url):  # db-query TODO: use, when db properly connected
                if True:
                    print("url not in db")
                    # yield scrapy.Request(short_url+"/", callback=self.parse_article,
                    #                      cb_kwargs=dict(short_url=short_url, long_url=long_url))
                    yield scrapy.Request(long_url, callback=self.parse_article,  cb_kwargs=dict(long_url=long_url, published_time=published_time))

                else:
                    print("url in db")
                    # utils.log_event(utils(), self.name, short_url, 'exists', 'info')
                    # logging.info('%s already in db', short_url)
                    utils.log_event(utils(), self.name,
                                    long_url, 'exists', 'info')
                    logging.info('%s already in db', long_url)

        # Quit the selenium driver and close every associated window
        driver.quit()

    def parse_article(self, response, long_url, published_time):
        utils_obj = utils()
        print("parsing article")

        def get_article_text():
            article_paragraphs = []
            tags = response.xpath('//div[@class="post hentry"]//p|a').extract()
            for tag in tags:
                line = ""
                tag_selector = Selector(text=tag)
                html_line = tag_selector.xpath('//*/text()').extract()
                for text in html_line:
                    line += text
                article_paragraphs.append(line)

            article_text = ""
            for paragraph in article_paragraphs:
                if paragraph:
                    article_text += paragraph + "\n\n"
            text = article_text.strip()
            if not text:
                utils.log_event(utils_obj, self.name,
                                long_url, 'text', 'warning')
                logging.warning("Cannot parse article text: %s", long_url)
            return text

        def get_pub_time():
            try:
                # input: 21.53.09"
                return datetime.strptime(published_time, '%d.%m.%Y')
            except:
                utils.log_event(utils_obj, self.name, long_url,
                                'published_time', 'warning')
                logging.warning("Cannot parse published time: %s", long_url)
                return None

        def filter(strings, substring):
            return [str for str in strings if substring in str]

        def get_keywords():
            # get script that contains the keywords
            keyword_script = filter(response.xpath(
                './/div/script/text()').extract(), "blogLabels.push")[0]
            # split to get one string per keyword and sort out strings that do not contain a keyword
            keywords_with_junk = filter(
                keyword_script.split("blogLabels.push('"),
                "');"
            )
            # Remove junk
            keywords = [re.sub(
                r"('\);|\n|PostillonAds.checkLabels\(blogLabels\);|\}\(\)\);)", '', str)
                .strip()
                for str in keywords_with_junk]
            return keywords

        item = ArticleItem()

        item['crawl_time'] = datetime.now()
        item['long_url'] = utils.add_host_to_url(utils_obj, long_url, root)
        item['short_url'] = long_url
        item['news_site'] = "postillon"
        item['title'] = utils.get_item_string(utils_obj, response, 'title', long_url, 'xpath',
                                              ['//meta[@property="og:title"]/@content'], self.name)
        item['authors'] = "Der Postillon"
        #    ['//meta[@name="author"]/@content'], self.name)
        item['description'] = utils.get_item_string(utils_obj, response, 'description', long_url, 'xpath',
                                                    ['//meta[@name="description"]/@content'], self.name)
        item['intro'] = utils.get_item_string(utils_obj, response, 'description', long_url, 'xpath',
                                              ['//meta[@name="description"]/@content'], self.name)
        item['text'] = get_article_text()

        item['keywords'] = get_keywords()

        item['published_time'] = get_pub_time()

        image_links = utils.get_item_list(utils_obj, response, 'image_links', long_url, 'xpath',
                                          ['//meta[@property="og:image"]/@content'], self.name)

        item['image_links'] = utils.add_host_to_url_list(
            utils_obj, image_links, root)  # if image_link starts with '/' prepend host

        item['links'] = utils.get_item_list(utils_obj, response, 'links', long_url, 'xpath',
                                            ['.//div[@itemprop="articleBody"]//a/@href'], self.name)

        # Print parsed article
        # print(item['crawl_time'], item['long_url'], item['short_url'], item['news_site'], item['title'], item['authors'],
        #     item['description'], item['intro'], item['text'], item['keywords'], item['keywords'], item['published_time'],
        #     item['image_links'], item['links'])

        # don't save article without title or text
        if item['title'] and item['text']:
            yield item
        else:
            logging.info("Cannot parse article: %s", long_url)
            utils.log_event(utils_obj, self.name, long_url,
                            'missingImportantProperty', 'info')
