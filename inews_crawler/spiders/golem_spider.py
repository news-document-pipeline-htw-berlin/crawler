import scrapy
from scrapy.spiders import Spider, Rule
from ..items import ArticleItem
from datetime import datetime, time
import locale
from ..utils import utils
import logging
import re


max_articles_per_month = 10     #articles to crawl per month
number_of_months = 1            #number of past months to crawl articles for

class PostsSpider(Spider):
    name = 'golem'


    def generate_archive_urls(self, number_of_months):
        '''
        Generate urls containing article links per month

        Parameters
        ----------
        number_of_months:
            number of months to generate article urls for
            
        Returns
        -------
        list of article links
        '''

        time = datetime.now()
        month = time.month
        month_str = str(month)

        if len(month_str) == 1:
            month_str = '0' + month_str 

        year = time.year - 2000
        links = []

        for _ in range(number_of_months):

            month_str = str(month)
            if len(month_str) == 1:
                month_str = '0' + month_str 

            links.append('https://www.golem.de/aa-{}{}.html'.format(year, month_str))
            if month - 1 == 0:
                month = 12
                year = year - 1
            else:
                month = month - 1
        
        return links
      

    def parse(self, response):
        '''
        Parse article links

        Parameters
        ----------
        response:
            Response of scrapy-Request
        '''
        #xpath: get links of articles
        for link in response.xpath('//*[@class="list-tickers"]/li[*]/h3/a/@href').getall()[0:max_articles_per_month]:
            yield self.request(url=link, callback=self.parse_article)

    
    def start_requests(self):
        '''
        Called by scrapy when the spider is opened
        '''
        for url in self.generate_archive_urls(number_of_months):
            yield self.request(url, self.parse)
    

    def request(self, url, callback):
        '''
        Request-Wrapper, sets cookies to bypass 'cookie-wall' and user agent

        Parameters
        ----------
        url:
            the URL of this request

        callback:
            the function that will be called with the response of this request

        Returns
        -------
        scrapy Request

        '''
        request = scrapy.Request(url=url, callback=callback)

        #set cookies to bypass 'allow cookies' wall
        request.cookies['iom_consent'] = '010fff0fff0fff&1603302347235'
        request.cookies['golem_consent20'] = 'cmp|200801'
        request.cookies['_sp_v1_consent'] = '1!0:-1:-1:-1'
        request.cookies['euconsent-v2'] = 'CO7pIXoO7pIXoAGABCENA8CsAP_AAE_AAAYgG1tf_X_fb3_j-_5999t0eY1f9_7_v-0zjgeds-8Nyd_X_L8X72M7vB36pq4KuR4Eu3LBAQdlHOHcTQmQ6IkVqTLsbk2Mq7NKJ7PEilMbM2dYGG1_n9XT_ZCY79__f__7__-_-___67f__-__3_vpgbSQQYAAoAAAIIAAAQKEQgAAgDEgAAAACKEQCgSQAJVAAMrgI4AAAAEBiAhAABACAhBgEAAAAASQBACAAggEABEAgABAAMAQAAIQAQWAEgIAAAIASEABEAEoEBBEABByABARAEEAIECAABcSGCEAIB4yA2ABQAFQAQwAmABcAEcAMsAagA7AB-AEYAI4AUsAq4BWwDeAJiATYAtEBbAC8wGBAMPAZEAzkBngDPhEB8AFQAVgAuACGAGQAMsAagA2QB2AD8AIwAUsAp4BVwDWAHVAPkAhsBDoCLwEiAJsATsApEBcgDAgGEgMPAZOAzkBnwgAGAbwBIQDQgkFMABAAC4AKAAqABkADgAHgAQAAiABUADAAGgAPIAhgCIAEwAJ8AVQBWACwAFwAN4AcwA9ACEAENAIgAiQBHQCWAJcATQApQBhgDIAGXANQA1QBsgDvAHsAPiAfYB-gEYAI4ASkAoIBSwCngFXALmAX4AwgBigDWAG0ANwAbwA9AB8gENgIdARUAi8BIgCYgEygJsATsAocBSICxQFsALkAXeAvMBgQDBgGEgMNAYeAyIBkgDJwGXAM5AZ8A04BrAUAEAMIBrIaBIACoAKwAXABDADIAGWANQAbIA7AB-AEFAIwAUsAp4BV4C0ALSAawA3gB1QD5AIbAQ6Ai8BIgCbAE7AKRAXIAwIBhIDDwGMAMnAZyAzwBnwYAMAbIA6gCQgF9AMjAaEKgOgAUABUAEMAJgAXABHADLAGoAOwAfgBGACOAFLAKvAWgBaQDeAJBATEAmwBTYC2AFyALzAYEAw8BkQDOQGeAM-HQXQAFwAUABUADIAHAAQAAiABUAC6AGAAYgA0AB4AD6AIYAiABMACfAFUAVgAsABcADEAGYAN4AcwA9ACEAEMAIgAR0AlgCYAE0AKUAWIAyABlADRAGoANkAb4A7wB7QD7AP0AjABHICUgJUAUEAp4BVwCxQFoAWkAuYBeQC_AGEAMUAbQA3EB0wHUAPQAhsBDoCIgEXgJBASIAmwBOwChwFNAKsAWLAtgC2QFwALkAXaAu8BeYDCQGGgMPAYkAxgBjwDJAGTgMqAZcAzkBnwDRAGkgNLAacA1gBsY8ACAiohA6AAWABQADIAIgAVAAuABiAEMAJgAVQAuABiADMAG8APQAjgBYgDKAGoAN8Ad4A_ACBgEYAI4ASkAoIBQwCngFXgLQAtIBcwC_AGEAMUAbQA6gB6AEggJEATYApoBYoC0YFsAW0AuABcgC7QGHgMSAZEAycBnIDPAGfANEAaSA0slAyAAQAAsACgAGQAOAAigBgAGIAPAAiABMACqAFwAMQAZgA2gCEAENAIgAiQBHAClAGEAMoAaoA2QB3gD8AIwARwAp4BV4C0ALSAYoA3AB1AD5AIdAReAkQBNgCxQFsALtAXmAw8BkQDJwGcgM8AZ8A1gmABARUUgjgALgAoACoAGQAOAAgABVADAAMQAaAA8gCGAIgATAAngBSACqAFgALgAYgAzABzAEIAIYARAApQBYgDKAGiANUAbIA74B9gH6ARgAjgBKQCggFDAKuAVsAuYBeQDCAG0ANwAegBDoCLwEiAJsATsAocBTQCtgFigLYAXAAuQBdoC8wGGgMPAYkAxgBkQDJAGTgMuAZyAzwBnwDSQGsANjKgAQGsgAA.YAAAAAAAAAAA'
        request.cookies['_sp_v1_opt'] = '1:login|true:last_id|11:'
        request.cookies['consentUUID'] = '964db86f-6456-4254-a762-fbad2acdb434'

        #set newest chrome user agent
        #https://www.whatismybrowser.com/guides/the-latest-user-agent/chrome
        request.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.111 Safari/537.36'
        return request


    def generate_short_url(self, url):
        '''
        Generate short article url

        Parameters
        ----------
        url:
            Golem url in long format
        
        Returns
        -------
        Golem url in short format
        '''
        pattern = re.compile(r'(\d+)(?!.*\d).html')
        num = pattern.search(url).group(1)
        return 'https://glm.io/{}'.format(str(num))



    def parse_article(self, response):
        '''
        Parse single article

        Parameters
        ----------
        response:
            Response of scrapy-Request

        '''
        utils_obj = utils()

        #xpath: get first heading of article page
        heading_1 = response.xpath('//*[@id="screen"]/div[2]/article/header/h1/span[1]/text()').get()
        
        #xpath: get second heading of article page
        heading_2 = response.xpath('/html/body/div[1]/div[2]/div[2]/div[2]/article/header/h1/span[3]/text()').get()

        #xpath: get first paragraph of article page
        intro = "\n".join(response.xpath('//*[@id="screen"]/div[2]/article/header/p/text() | //*[@id="screen"]/div[2]/article/header/p/a/text()').extract())

        #xpath: get authors of article page
        authors = response.xpath('//*[@id="screen"]/div[2]/article/header/div[1]/span[4]/text() | //*[@id="screen"]/div[2]/article/header/div[1]/span[4]/a/text() | //*[@id="screen"]/div[2]/article/header/div[1]/span[3]/a/text()').extract()
        if ' veröffentlicht am ' in authors:
            authors.remove(' veröffentlicht am ')

        #xpath: get publishing time of article page
        published_time = response.xpath('//*[@id="screen"]/div[2]/article/header/div[1]/time/text()').get()

        #xpath: get wrapper containing article text
        text_wrapper = response.xpath('//*[@id="screen"]/div[2]/article/div[1]')

        #css: get all paragraphs and headlines the text wrapper contains
        texts = "\n".join(text_wrapper.css('p::text, p a::text, h3::text').extract())

        #xpath/css: get all links from the text header and the text wrapper
        links = list(set(response.xpath('//*[@id="screen"]/div[2]/article/header/p/a/@href').extract() + text_wrapper.css('p a::attr(href)').extract()))

        short_url = self.generate_short_url(response.url)

        #xpath: get all images of the article page
        images = response.xpath('//*[@class="hero"]/img/@src').extract()


        # Preparing for Output -> see items.py
        item = ArticleItem()

        item['crawl_time'] = datetime.now()
        item['long_url'] = response.url
        item['short_url'] = short_url

        item['news_site'] = "golem"
        item['title'] = heading_1 + ": " + heading_2

        item['authors'] = authors

        item['description'] = intro

        item['intro'] = intro
        item['text'] = texts

        #item['keywords'] = key_words

        timeformat = r"%d. %B %Y, %H:%M Uhr"
        #set locale to german for correct date parsing
        locale.setlocale(locale.LC_TIME, 'de_DE')
        item['published_time'] = datetime.strptime(published_time, timeformat)

        item['image_links'] = images

        item['links'] = links

        # don't save article without title or text
        if item['title'] and item['text']:
            yield item
        else:
            logging.info("Cannot parse article: %s", short_url)
            utils.log_event(utils_obj, self.name, short_url, 'missingImportantProperty', 'info')


        


       

