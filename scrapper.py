# coding=UTF-8

import requests
import re
from datetime import date as dt
from bs4 import BeautifulSoup
import urlparse
from dateutil.relativedelta import relativedelta
import pandas


def stringify_child(child):
    if child.string:
        return unicode(child.string.strip())
    if hasattr(child, 'children') and child.children:
        return [stringify_child(x) for x in child.children]


def table_into_json(table):
    result = []
    trs = table.find_all('tr')
    for tr in trs:
        result.append([stringify_child(td) for td in tr.find_all('td')])
    return result


def as_float(text):
    if text:
        return float(re.sub("[^0-9\,\.]", "", text).replace(",", "."))
    return None


def as_int(text):
    if text:
        return int(re.sub("[^0-9]", "", text))
    return None


def as_date(text):
    quarter = int(text[0])
    year = int(text[-4:])
    return dt(year, quarter * 3, 1) + relativedelta(months=1)


def to_soup(url):
    page = requests.get(url)
    return BeautifulSoup(page.content, "lxml")


def parse_invest_html(url):
    soup = to_soup(url)
    body = soup.find_all('div', {"data-config-table-container": "propertyListFull"})[0].tbody
    links = []
    for row in body.find_all('tr'):
        potential_links = row.find_all('a', href=True)
        if len(potential_links) == 2:
            links.append(make_link(potential_links[1]))
        else:
            links.append(make_link(potential_links[0]))
    return links


def make_link(link):
    return urlparse.urljoin("https://rynekpierwotny.pl/", link['href'])


def parse_search_page(page, region=11158, rooms_0=3, rooms_1=3, price_m2_1=7000):
    url = ("https://rynekpierwotny.pl/oferty/?type=&region={region}"
           "&distance=0&price_0=&price_1=&area_0=&area_1=&rooms_0={rooms_0}&rooms_1={rooms_1}"
           "&construction_end_date=&price_m2_0=&price_m2_1={price_m2_1}&floor_0=&floor_1="
           "&offer_size=&keywords=&is_luxury=&page={page}&is_mdm=&is_holiday=&lat=&lng=&sort=").format(
        region=region,
        rooms_0=rooms_0,
        rooms_1=rooms_1,
        price_m2_1=price_m2_1,
        page=page
    )
    soup = to_soup(url)
    links = []
    for result in soup.find_all('h2', {'class': 'offer-item-name'}):
        links.append(make_link(result.a))
    return links


def search_all_investments(region=11158, rooms_0=3, rooms_1=3, price_m2_1=7000):
    i = 1
    results = []
    partial_results = parse_search_page(i, region, rooms_0, rooms_1, price_m2_1)
    while partial_results:
        results += partial_results
        i += 1
        partial_results = parse_search_page(i, region, rooms_0, rooms_1, price_m2_1)
    return results


def as_dict(table):
    result = {}
    for key, value in table:
        if isinstance(key, list):
            key = key[1]
        result[key] = value
    return result


def retrieve_meta(soup, id, tag_name='id'):
    metas = soup.find_all('meta', {tag_name: id})
    if metas:
        return metas[0]['content']
    return None


def parse_parking_place(str):
    str_no_whitespace = re.sub("\s|\.", "", str)
    ranges = [as_float(x) for x in re.findall("[0-9]+", str_no_whitespace)]
    ranges = [x for x in ranges if x >= 1000]
    if ranges:
        return min(ranges)
    return None


def parse_parking_places(l):
    parsed_places = [parse_parking_place(x) for x in l] if isinstance(l, list) else [parse_parking_place(l)]
    parsed_places = [place for place in parsed_places if place]
    if parsed_places:
        return min(parsed_places)
    return None


def parse_details_html(url):
    try:
        soup = to_soup(url)

        basic_data = as_dict(table_into_json(soup.find_all('section', {'id': 'szczegoly-oferty'})[0].table))
        extended_data_sections = soup.find_all('section', {'id': 'dodatkowe-oplaty'})
        extended_data = {}
        if extended_data_sections:
            extended_data = as_dict(table_into_json(extended_data_sections[0].table))

        return {
            u"Link": url,
            u"Region": retrieve_meta(soup, 'dimension-region'),
            u"Ulica": retrieve_meta(soup, "streetAddress", "itemprop").lower().strip("ul.").strip(),
            u"Cena mieszkania": as_int(retrieve_meta(soup, 'dimension-price')),
            u"Cena za metr": as_int(retrieve_meta(soup, 'dimension-price-m2')),
            u"Powierzchnia": as_float(retrieve_meta(soup, 'dimension-area')),
            u"Pokoje": as_int(retrieve_meta(soup, 'dimension-rooms')),
            u'Cena parkingu': parse_parking_places(basic_data['Miejsca postojowe:'][1]),
            u'Piętro:': as_int(retrieve_meta(soup, 'dimension-floor')),
            u"Koszty dodatkowe": sum([as_int(value) for value in extended_data.values()]),
            u"Długosć geograficzna": as_float(retrieve_meta(soup, 'longitude', 'itemprop')),
            u"Szerokość geograficzna": as_float(retrieve_meta(soup, 'latitude', 'itemprop')),
            u"Termin": as_date(basic_data['Realizacja inwestycji:'][-16:-6])
        }
    except requests.exceptions.ConnectionError:
        return url
    except Exception, e:
        raise Exception("Failed to fetch %s" % url, e)


def flatten_list(l):
    return [item for sublist in l for item in sublist]


def scrap():
    from multiprocessing import Pool
    pool = Pool(30)

    investments = search_all_investments()
    print "There are %s investments found" % len(investments)

    apartments = flatten_list(pool.map(parse_invest_html, investments))
    apartments_details = []
    while apartments:
        print "Fetching %s apartaments" % len(apartments)
        results = pool.map(parse_details_html, apartments)
        apartments_details += [result for result in results if isinstance(result, dict)]
        apartments = [result for result in results if isinstance(result, unicode) or isinstance(result, str)]

    df = pandas.DataFrame(apartments_details)
    df.to_pickle("/home/ppastuszka/Dokumenty/apartmentdata.pkl")


scrap()
# print parse_details_html(
#     "https://rynekpierwotny.pl/oferty/emmerson-lumico-sp-z-oo/strycharska-10-krakow-podgorze/384257")
