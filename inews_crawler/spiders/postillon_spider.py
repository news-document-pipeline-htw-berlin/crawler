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
testrun_years_and_months = 0        # limits the number of closed year- and month-archive-entities to open (and reveal contained months/articles)
testrun_articles = 0                # limits the article links to crawl to this number. if zero, no limit.
                                    # For deployment: don't forget to set the testrun variables to zero
testrun_article_url = False         # 'https://www.der-postillon.com/2020/11/sonntagsfrage-nerze.html'  # Only scrape the specified article

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
            driver = webdriver.Firefox(desired_capabilities=desired_capabilities)
            return driver

        driver = init_selenium_driver()

        driver.get(root)
        elements = driver.find_elements_by_class_name('closed') # also finds closed months inside closed years
        
        elements = elements[:testrun_years_and_months] # crawl limit
        for element in elements:
            try:
                driver.execute_script("arguments[0].click();", element) # element.click() causes Exception: "could not be scrolled into view"
            except Exception as e:
                print(e)


        # Hand-off between Selenium and Scrapy
        sel = Selector(text=driver.page_source)
        # linklist = sel.xpath('//ul[@class="month-inner"]//li/a/@href').extract()
        articleList = sel.xpath('//ul[@class="month-inner"]//li/a')


        articleList = utils.limit_crawl(articleList,testrun_articles)  # TODO apply crawl limit also for Selenium link crawling
        
        if articleList:
            for article in articleList:
                long_url = article.xpath('./@href').extract()[0]
                # TODO: check if list is empty
                # long_url = article.xpath('./@href').extract()
                # long_url = long_url[0] if long_url != [] else ''
                published_time = article.xpath('.//div[@class="date"]/text()').extract()
                published_time = published_time[0] if len(published_time) > 0 else ''
                
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
                    utils.log_event(utils(), self.name, long_url, 'exists', 'info')
                    logging.info('%s already in db', long_url)

        # Quit the selenium driver and close every associated window
        driver.quit()


    def parse_article(self, response, long_url, published_time):
        utils_obj = utils()

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
                utils.log_event(utils_obj, self.name, long_url, 'text', 'warning')
                logging.warning("Cannot parse article text: %s", long_url)
            return text


        def get_pub_time():
            try:
                return datetime.strptime(published_time, '%d.%m.%Y')  # input: 21:53:09"
            except:
                utils.log_event(utils_obj, self.name, long_url, 'published_time', 'warning')
                logging.warning("Cannot parse published time: %s", long_url)
                return None


        # Preparing for Output -> see items.py
        item = ArticleItem()

        item['crawl_time'] = datetime.now()
        item['long_url'] = utils.add_host_to_url(utils_obj, long_url, root)
        item['short_url'] = long_url # TODO: check if null is preferred

        item['news_site'] = "postillon"
        item['title'] = utils.get_item_string(utils_obj, response, 'title', long_url, 'xpath',
                                              ['//meta[@property="og:title"]/@content'], self.name)
        item['authors'] = "Der Postillon" #utils.get_item_list(utils_obj, response, 'authors', long_url, 'xpath',
                                          #    ['//meta[@name="author"]/@content'], self.name)
        item['description'] = utils.get_item_string(utils_obj, response, 'description', long_url, 'xpath',
                                                ['//meta[@name="description"]/@content'], self.name)
        item['intro'] = utils.get_item_string(utils_obj, response, 'description', long_url, 'xpath',
                                                ['//meta[@name="description"]/@content'], self.name) #utils.get_item_string(utils_obj, response, 'intro', long_url, 'xpath',
                                              # ['//article/p[@class="intro "]/text()'], self.name)
        item['text'] = get_article_text()

        # TODO: parse keywords from javascript
        # keywords script example
        # <script type="text/javascript">
        #     (function() {
        #       var blogLabels = [];
        #       blogLabels.push('Corona');
        #       blogLabels.push('Coronavirus');
        #       blogLabels.push('Leipzig');
        #       blogLabels.push('Linksextremismus');
        #       blogLabels.push('Politik');
        #       blogLabels.push('Polizei');
        #       PostillonAds.checkLabels(blogLabels);
        #     }());
        #   </script>
        # keywords = utils.get_item_list_from_str(utils_obj, response, 'keywords', long_url, 'xpath',
                                                # ['//meta[@name="keywords"]/@content'],', ', self.name)
        # item['keywords'] = list(set(keywords) - {"taz", "tageszeitung "})
        item['keywords'] = ["keyword1", "keyword2"] #list(set(keywords) - {"taz", "tageszeitung "})

        item['published_time'] = get_pub_time()

        image_links = utils.get_item_list(utils_obj, response, 'image_links', long_url, 'xpath',
                                          ['//meta[@property="og:image"]/@content'], self.name)

        item['image_links'] = utils.add_host_to_url_list(utils_obj, image_links, root) # if image_link starts with '/' prepend host

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
            utils.log_event(utils_obj, self.name, long_url, 'missingImportantProperty', 'info')

