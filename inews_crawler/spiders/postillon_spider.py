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

# For deployment: don't forget to set the testrun variables to 0
# limits number of articles. If 0, no limit.
testrun_articles = 10
# Only scrape the specified article. Full URL required or False/0 to disable this limit
# 'https://www.der-postillon.com/2020/11/agent-smith.html'
testrun_article_url = False

year_to_crawl = 2020  # If False or 0, crawl all years
# limits to crawl only articles of the year beginning with the specified month (newer or equal). If False or 0, crawl entire year. Requires year_to_crawl to not be False
limit_min_month_of_year_to_crawl = 9


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

        def get_closed_elements():
            # Get all closed months of year to crawl, that are newer or equal to the limit specified by limit_min_month_of_year_to_crawl
            if limit_min_month_of_year_to_crawl:
                # get year
                closed_months_of_year_to_crawl = driver.find_element_by_class_name(
                    'year-' + str(year_to_crawl))

                # Get closed months
                xpath = ".//li[contains(@class, 'closed') and (contains(@class, 'month-12')"
                for month in range(limit_min_month_of_year_to_crawl, 12):
                    xpath += " or contains(@class, 'month-" + \
                        f'{month+1:02d}' + "')"
                xpath = xpath + ")]"

                closed_elements = closed_months_of_year_to_crawl.find_elements_by_xpath(
                    xpath)

            # Get all closed months of year to crawl
            elif year_to_crawl:
                closed_elements = driver.find_element_by_class_name(
                    'year-' + str(year_to_crawl)).find_elements_by_class_name('closed')

            # Get all closed years/months of the entire archive
            else:
                # also finds closed months inside closed years
                closed_elements = driver.find_elements_by_class_name('closed')

            print(len(closed_elements))
            return closed_elements

        def click_elements(elements):
            for element in elements:
                try:
                    # element.click() causes Exception: "could not be scrolled into view"
                    driver.execute_script("arguments[0].click();", element)
                    print("click")
                except Exception as e:
                    print(e)

        driver = init_selenium_driver()
        driver.get(root)

        # Open closed years/months to load articles
        click_elements(get_closed_elements())

        # Hand-off between Selenium and Scrapy
        sel = Selector(text=driver.page_source)

        articleList = sel.xpath('//ul[@class="month-inner"]//li/a')

        articleList = utils.limit_crawl(articleList, testrun_articles)

        if articleList:
            for article in articleList:
                long_url = article.xpath('./@href').extract()[0]
                published_time = article.xpath(
                    './/div[@class="date"]/text()').extract()
                published_time = published_time[0] if len(
                    published_time) > 0 else ''

                if long_url and not utils.is_url_in_db(long_url):
                    yield scrapy.Request(long_url, callback=self.parse_article,  cb_kwargs=dict(long_url=long_url, published_time=published_time))

                else:
                    print("url in db")
                    utils.log_event(utils(), self.name,
                                    long_url, 'exists', 'info')
                    logging.info('%s already in db', long_url)

        # Quit the selenium driver and close every associated window
        driver.quit()

    def parse_article(self, response, long_url, published_time):
        utils_obj = utils()
        print("parsing article" + long_url)

        def get_article_text():
            article_paragraphs = []
            tags = response.xpath(
                '//div[@class="post hentry"]//p|a|b').extract()

            for tag in tags:
                line = ""
                tag_selector = Selector(text=tag)
                text_list = tag_selector.xpath('//*/text()').extract()
                for text_part in text_list:
                    line += text_part
                article_paragraphs.append(line)

            article_text = ""
            for paragraph in article_paragraphs:
                if paragraph:
                    article_text += paragraph + "\n\n"
            text = article_text.strip()

            if not text:
                # Alternative article layout. Examples https://www.der-postillon.com/2019/11/deutsche-bahn-hack.html , 'https://www.der-postillon.com/2020/02/fehler-stabhochsprung.html'
                text_list = response.xpath(
                    '//div[@itemprop="articleBody"]//text()').extract()

                # slicing off after length computation
                # Slice off everything after "Lesen Sie auch:"
                begin_slice = '\nLesen Sie auch: '
                text_list = text_list[:text_list.index(begin_slice)]

                # Slice off credits
                len_text_list = len(text_list)
                for i in range(1, 4):
                    if any(substring in text_list[len_text_list-i] for substring in ['ssi', 'dan', 'pfg', 'fed', 'Foto', '\n']):
                        text_list = text_list[:len_text_list-i]

                # Combine text_list
                for text_part in text_list:
                    text += text_part
                text = text.strip()

                # Could not parse text
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

        # TODO
        def get_authors():
            return ['Alexander Bayer', 'Dan Eckert']

        item = ArticleItem()

        item['crawl_time'] = datetime.now()
        item['long_url'] = utils.add_host_to_url(utils_obj, long_url, root)
        item['short_url'] = long_url
        item['news_site'] = "postillon"
        item['title'] = utils.get_item_string(utils_obj, response, 'title', long_url, 'xpath',
                                              ['//meta[@property="og:title"]/@content'], self.name)
        item['authors'] = get_authors()  # ["Der Postillon"]
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
