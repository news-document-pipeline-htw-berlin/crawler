import scrapy
from scrapy import Selector
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import logging
from datetime import datetime
from ..items import ArticleItem
from ..utils import utils
import time
import re

root = 'https://www.der-postillon.com/p/das-postillon-archiv.html'

# For deployment: don't forget to set the testrun variables to 0
# limits number of articles. If 0/False, no limit.
testrun_articles = False
# Only scrape the specified article. Full URL required or False/0 to disable this limit
# 'https://www.der-postillon.com/2020/11/agent-smith.html'
testrun_article_url = False

year_to_crawl = False  # If False or 0, crawl all years
# limits to crawl only articles of the year beginning with the specified month (newer or equal). If False or 0, crawl entire year. Requires year_to_crawl to not be False
limit_min_month_of_year_to_crawl = False

CURRENT_YEAR = 2020


class PostillonSpider(scrapy.Spider):
    name = "postillon"
    start_url = root

    def start_requests(self):
        """
        Generates a request for the URL specified in start_url and defines self.parse as callback function, if testrun_article_url is not defined. 
        Else a request for testrun_article_url is genereated and self.parse_article is defined as callback function.
        """
        if testrun_article_url:
            yield scrapy.Request(testrun_article_url, callback=self.parse_article, cb_kwargs=dict(long_url=testrun_article_url, published_time="13.11.2020"))
        else:
            yield scrapy.Request(self.start_url, callback=self.parse)

    def parse(self, response):
        """ 
        Scrape archive for articles
        Parameters
        ----------
        self:
            the PostillonSpider object
        response:
            The response from a scrapy request
        """
        def init_selenium_driver():
            """
            Initialize and return a firefox selenium driver.

            Returns
            -------
            A firefox selenium driver
            """
            firefoxOptions = webdriver.FirefoxOptions()
            firefoxOptions.headless = True
            desired_capabilities = firefoxOptions.to_capabilities()
            driver = webdriver.Firefox(
                desired_capabilities=desired_capabilities)

            #
            return driver

        def get_closed_elements():
            """
            Returns all or some closed year and month elements, depending on the limit definitions.

            Returns
            -------
            All or some closed year and month elements, depending on the limit definitions.
            """
            # Get all closed months of year to crawl, that are newer or equal to the limit specified by limit_min_month_of_year_to_crawl
            if limit_min_month_of_year_to_crawl:
                # get year
                element_of_year_to_crawl = driver.find_element_by_class_name(
                    'year-' + str(year_to_crawl))

                # Get closed months
                xpath = ".//li[contains(@class, 'closed') and (contains(@class, 'month-12')"
                for month in range(limit_min_month_of_year_to_crawl-1, 12):
                    xpath += " or contains(@class, 'month-" + \
                        f'{month+1:02d}' + "')"
                xpath = xpath + ")]"

                closed_elements = element_of_year_to_crawl.find_elements_by_xpath(
                    xpath)
                closed_elements.append(element_of_year_to_crawl)

            # Get all closed months of year to crawl
            elif year_to_crawl:
                element_of_year_to_crawl = driver.find_element_by_class_name(
                    'year-' + str(year_to_crawl))

                closed_elements = element_of_year_to_crawl.find_elements_by_class_name(
                    'closed')
                closed_elements.append(element_of_year_to_crawl)

            # Get all closed years/months of the entire archive
            else:
                # also finds closed months inside closed years
                closed_elements = driver.find_elements_by_class_name('closed')

            return closed_elements

        def waitForLoad():
            """
            Wait until at 1 article per year has been loaded. 
            If the current year is being crawled wait until an article of january or limit_min_month_of_year_to_crawl 
            has been loaded (Because the current month of the current year is already loaded on page load).

            """
            TIMEOUT = 10
            wait = WebDriverWait(driver, TIMEOUT)
            try:
                xpath = "//a/div/div/div[contains(@class, 'date') and contains(string(), '."
                if year_to_crawl:
                    # If the current year is crawled wait for an article of the first month to be loaded. 
                    # This is necessary because the current month is already loaded on page load.
                    if year_to_crawl == CURRENT_YEAR:
                        if limit_min_month_of_year_to_crawl:
                            xpath += str(limit_min_month_of_year_to_crawl) + "."
                        else:
                            xpath += str(1) + "."

                    xpath += str(year_to_crawl) + "')]"
                    wait.until(EC.presence_of_element_located(
                        (By.XPATH, xpath)))

                # Wait for 1 artile per year
                else:
                    base_xpath = xpath
                    for i in range(2008, CURRENT_YEAR+1):
                        xpath = base_xpath + str(i) + "')]"
                        wait.until(EC.presence_of_element_located(
                            (By.XPATH, xpath)))

            except TimeoutException as e:
                logging.warning(
                    "TimeoutException has been thrown while waiting for articles to load: %s", e)

        def click_elements(elements):
            """"
            Click all elements in elements

            Parameters
            ----------
            elements:
                HTML Elements to be clicked
            """
            for element in elements:
                try:
                    # element.click() causes Exception: "could not be scrolled into view"
                    driver.execute_script("arguments[0].click();", element)
                    print("click: " +
                          element.get_attribute('class').split()[1])

                except Exception as e:
                    logging.warning(
                        "An exception has been thrown while clicking closed years/months: %s", e)

        driver = init_selenium_driver()
        driver.get(root)

        # Close all years/months
        click_elements(driver.find_elements_by_class_name('open'))

        # Open closed years/months to load articles
        click_elements(get_closed_elements())

        # Wait for articles to be loaded
        waitForLoad()

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
        """
        Parse the article contained in response and save the results (and long_url, published_time) in an ArticleItem.

        Parameters
        ----------
        self:
            the PostillonSpider object
        response:
            The response from a scrapy request
        long_url:
            Url of the article to be parsed
        published_time:
            Published time of the article to be parsed
        """

        utils_obj = utils()
        print("parsing article: " + long_url)

        def get_article_text():
            """
            Returns the text of the article

            Returns
            -------
            The text of the article
            """
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
                if begin_slice in text_list:
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
            """
            Returns the published time of the article

            Returns
            -------
            The published time of the article
            """
            try:
                # input: 21.53.09"
                return datetime.strptime(published_time, '%d.%m.%Y')
            except:
                utils.log_event(utils_obj, self.name, long_url,
                                'published_time', 'warning')
                logging.warning("Cannot parse published time: %s", long_url)
                return None

        def filter(strings, substring):
            """
            Filter strings by substring

            Parameters
            ----------
            strings:
                Strings to be filtered
            substring:
                Substring that must be in a string so that the string is not filtered out.

            Returns
            -------
            String array containing all strings of strings, that include substring 
            """

            return [str for str in strings if substring in str]

        def get_keywords():
            """
            Returns the keywords of the article

            Returns
            -------
            The keywords of the article
            """

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

        def get_authors():
            """
            Returns the authors of the article

            Returns
            -------
            The authors of the article
            """

            authors = []
            author_dict = {
                "ssi": "Stefan Sichermann",
                "dan": "Dan Eckert",
                "pfg": "Peer Gahmert und Phillip Feldhusen",
                "fed": "Alexander Bayer",
                "tla": "Tobias Lauterbach",
                "swo": "Sebastian Wolking",
                "bep": "Bernhard Pöschla",
                "jki": "Julia Kiesselbach",
                "adg": "Daniel Al-Kabbani",
                "up": "Die UpTicker-Redaktion",
                "mate": "Mate Tabula",
                "lor": "Laura Orlik",
                "vwi": "Valentin Witt",
                "coe": "Cornelius Oettle",
                "sha": "Simon Hauschild",
                "shp": "Selim Han Polat",
                "ejo": "Ernst Jordan"
            }

            potential_credit_strings = response.xpath(
                '//div[@itemprop="articleBody"]//span/text()').extract()

            for potential_credit_string in potential_credit_strings:
                for author_key in list(author_dict.keys()):
                    if author_key in potential_credit_string:
                        authors.append(author_dict[author_key])

            if len(authors) == 0:
                authors.append("Der Postillon")

            return authors

        item = ArticleItem()

        item['crawl_time'] = datetime.now()
        item['long_url'] = utils.add_host_to_url(utils_obj, long_url, root)
        item['short_url'] = long_url
        item['news_site'] = "postillon"
        item['title'] = utils.get_item_string(utils_obj, response, 'title', long_url, 'xpath',
                                              ['//meta[@property="og:title"]/@content'], self.name)
        item['authors'] = get_authors()
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

        # Only save articles without title or text
        if item['title'] and item['text']:
            yield item
        else:
            logging.info("Cannot parse article: %s", long_url)
            utils.log_event(utils_obj, self.name, long_url,
                            'missingImportantProperty', 'info')
