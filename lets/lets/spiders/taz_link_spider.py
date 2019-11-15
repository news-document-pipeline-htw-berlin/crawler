import scrapy
from scrapy.loader import ItemLoader
from ..items import LinkItems

root = 'https://taz.de'
testrun = 3                     # limits the categories to crawl to this number. if zero, no limit.


class Taz_Links_Spider(scrapy.Spider):
    name = "taz_links"
    start_url = root

    def start_requests(self):
        yield scrapy.Request(self.start_url, callback=self.parse)

    def parse(self, response):
        categories = response.xpath('//ul[@class="news navbar newsnavigation"]/li/a/@href').extract()
        categories.append(root)
        if testrun>0 and testrun<len(categories):
            categories = categories[:testrun]
        for cat in categories:
            if cat[0]=='/':
                cat = root + cat        # for relative paths it is necessary to add scheme and host
            yield scrapy.Request(url=cat, callback=self.parse_categories)


    def parse_categories(self, response):
        l = ItemLoader(item=LinkItems(), response=response)
        item=LinkItems()

        def getLinkselector():
            # taz.de has different classes of links which direct to an article
            linkclasses = [
                "objlink report article",
                "objlink report article leaded pictured",
                "objlink brief report article leaded",
                "objlink brief report article pictured",
                "objlink subjective commentary article",
                "objlink brief subjective column article leaded"]

            linkselector = '//a[(@class=\"'
            linkselector_middle = '\") or (@class=\"'
            linkselector_end = '\")]/@href'
            for linkclass in linkclasses:
                linkselector+=linkclass + linkselector_middle
            linkselector = linkselector[:-len(linkselector_middle)] + linkselector_end
            return linkselector

        linklist = response.xpath(getLinkselector)
        # DB-Query for Duplicates?
        item['url'] = linklist
        yield item
