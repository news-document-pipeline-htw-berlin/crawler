import scrapy
from scrapy import Selector
from datetime import datetime
import logging
from ..items import ArticleItem
from ..utils import utils
import sys

root = 'https://sueddeutsche.de'
short_url_regex = "\d(\.|\d)+$" # helps converting long to short url: https://sueddeutsche.de/1.3456789
full_article_addition = '-0'    # if article extends over multiple pages this url addition will get the full article

testrun_cats = 5                # limits the categories to crawl to this number. if zero, no limit.
testrun_arts = 5                # limits the article links to crawl per category page to this number. if zero, no limit.

limit_pages = 1                 # additional category pages of 50 articles each. Maximum of 400 pages
                                # => 1. building the archive: 400
                                # => 2. daily use: 0 or 1
                                # don't forget to set the testrun variables to zero


class SueddeutscheSpider(scrapy.Spider):
    name = "sueddeutsche"
    name_short = "sz"
    start_urls = [root]

    # scrape main page for categories
    def parse(self, response):
        departments = response.css("#header-departments .nav-item-link").xpath("@href").extract()
        departments = utils.limit_crawl(departments,testrun_cats)

        for department_url in departments:
            dep = department_url.split("/")[-1]
            yield scrapy.Request(department_url,
                                 callback=self.parse_category,
                                 cb_kwargs=dict(department=dep, department_url=department_url))

    # scrape category pages for articles
    def parse_category(self, response, department, department_url):

        departmentIds = {
            "politik": "sz.2.236",
            "wirtschaft": "sz.2.222",
            "meinung": "sz.2.238",
            "panorama": "sz.2.227",
            "sport": "sz.2.235",
            "muenchen": "sz.2.223",
            "bayern": "sz.2.226",
            "kultur": "sz.2.237",
            "leben": "sz.2.225",
            "wissen": "sz.2.240",
            "digital": "sz.2.233",
            "karriere": "sz.2.234",
            "reise": "sz.2.241",
            "auto": "sz.2.232",
            "medien": "sz.2.221",
            "geld": "sz.2.229"
        }

        utils_obj = utils()

        articles = response.css(".sz-teaser")
        links = articles.xpath("@href").extract()

        links = utils.limit_crawl(links,testrun_arts)


        for i in range(len(links)):
            short_url = utils.get_short_url(links[i],root, short_url_regex)
            if short_url and not utils.is_url_in_db(short_url):            #db-query
                description = utils.get_item_string(utils_obj, articles[i], 'description', department_url, 'css',
                                                    [".sz-teaser__summary::text"], self.name_short)
                yield scrapy.Request(links[i]+full_article_addition, callback=self.parse_article,
                                     cb_kwargs=dict(description=description, long_url=links[i], short_url=short_url,
                                                    dep=department))
            else:
                utils.log_event(utils_obj, self.name_short, short_url, 'exists', 'info')
                logging.info("%s already in db", short_url)
    


    def parse_article(self, response, description, short_url, long_url, dep):
        utils_obj = utils()

        def get_intro():
            article_intro = response.css(".css-korpch")
            paragraphs = article_intro.css('div p::text').extract() + article_intro.css('div p b::text').extract()
            list_items = article_intro.css('div ul li::text').extract()

            intro = ' '.join(paragraphs + list_items)
            intro = utils.remove_whitespace(intro)

            if not intro:
                utils.log_event(utils_obj, self.name_short, short_url, 'intro', 'warning')
                logging.warning("Cannot parse intro: %s", short_url)
                intro = ""

            return intro

        def get_article_text():
            article_wrapper = response.xpath('//*[@itemprop="articleBody"]')
            article_parts = article_wrapper.css('p.css-13wylk3::text, p.css-13wylk3 h3::text, p.css-13wylk3 b::text, p.css-13wylk3 a::text, p.css-13wylk3 i::text').extract()

            text = ' '.join(article_parts)
            text = utils.remove_whitespace(text)

            if not text:
                utils.log_event(utils_obj, self.name_short, short_url, 'text', 'warning')
                logging.warning("Cannot parse article text: %s", short_url)

            return text

        def get_pub_time():
            time_str = response.xpath('//time/@datetime').get()
            try:
                return datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')  # "2019-11-21 21:53:09"
            except _:
                utils.log_event(utils_obj, self.name_short, short_url, 'published_time', 'warning')
                logging.warning("Cannot parse published time: %s", short_url)
                return None


        # don't save paywalled article parts
        paywall = response.xpath('//offer-page').get()
        if not paywall:

            item = ArticleItem()

            item['crawl_time'] = datetime.now()
            item['long_url'] = long_url
            item['short_url'] = short_url

            item['news_site'] = "sz"
            item['title'] = utils.get_item_string(utils_obj, response, 'title', short_url, 'xpath',
                                                  ['//meta[@property="og:title"]/@content'], self.name_short)
            item['authors'] = utils.get_item_list(utils_obj, response, 'authors', short_url, 'xpath',
                                                    ['//meta[@name="author"]/@content'], self.name_short)

            item['description'] = description
            item['intro'] = get_intro()
            item['text'] = get_article_text()

            keywords = utils.get_item_list_from_str(utils_obj, response, 'keywords', short_url, 'xpath',
                                                            ['//meta[@name="keywords"]/@content'],',', self.name_short)
            item['keywords'] = list(set(keywords) - {"Süddeutsche Zeitung"})

            item['published_time'] = get_pub_time()
            item['image_links'] = utils.get_item_list(utils_obj, response, 'image_links', short_url, 'xpath',
                                                               ['//meta[@property="og:image"]/@content'], self.name_short)

            links =  utils.get_item_list(utils_obj, response, 'links', short_url, 'xpath',
                                         ['//div[@class="sz-article__body sz-article-body"]/p/a/@href'], self.name_short)
            item['links'] = utils.add_host_to_url_list(utils_obj, links, root)

            # don't save article without title or text
            if item['title'] and item['text']:
                    yield item
            else:
                logging.info("Cannot parse article: %s", short_url)
                utils.log_event(utils_obj, self.name_short, short_url, 'missingImportantProperty', 'info')
        else:
            utils.log_event(utils_obj, self.name_short, short_url, 'paywall', 'info')
            logging.info("Paywalled: %s", short_url)
