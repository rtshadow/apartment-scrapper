# coding: utf-8
import math
import os
from datetime import date
from dateutil.relativedelta import relativedelta
from multiprocessing import Pool

import googlemaps
import numpy as np
import pandas

from utils import high_traffic_date, low_traffic_date, weekend_midday_date

mdm_limit = 5247
mdm_discount = 0.1
monthly_rent = 900
client_key = os.environ["GOOGLE_SERVER_KEY"]
target_location = u"Rakowicka 7, Kraków"

data = pandas.read_pickle("/home/ppastuszka/Dokumenty/apartmentdata.pkl")

cleaned_data = data[np.isfinite(data['Cena mieszkania'])]
cleaned_data['Cena parkingu'].fillna(0, inplace=True)
cleaned_data['Koszty dodatkowe'].fillna(cleaned_data['Koszty dodatkowe'].mean(), inplace=True)


def calculate_mdm_discount(row):
    if row['Cena za metr'] <= mdm_limit:
        discounted_area = min(row['Powierzchnia'], 50)
        return discounted_area * mdm_discount * row['Cena za metr']
    return 0


cleaned_data[u"Zniżka MDM"] = cleaned_data.apply(calculate_mdm_discount, axis=1)
cleaned_data[u'Cena mieszkania z MDM'] = cleaned_data['Cena mieszkania'] - cleaned_data[u"Zniżka MDM"]
cleaned_data['Cena mieszkania + parking MDM'] = cleaned_data['Cena mieszkania z MDM'] + cleaned_data['Cena parkingu']
cleaned_data['Termin'] = pandas.to_datetime(cleaned_data['Termin'])


def months_left(to_date):
    delta = relativedelta(to_date, date.today())
    if delta.years >= 0 and delta.months >= 0 and delta.days >= 0:
        return delta.years * 12 + delta.months + (1 if delta.days > 0 else 0)
    return 0


cleaned_data[u'Miesięcy do oddania'] = cleaned_data['Termin'].apply(months_left)
cleaned_data[u'Strata na czynszu'] = cleaned_data[u'Miesięcy do oddania'] * monthly_rent

cleaned_data[u'Cena łączna z MDM'] = cleaned_data['Cena mieszkania + parking MDM'] + cleaned_data['Koszty dodatkowe'] + \
                                     cleaned_data['Strata na czynszu']

cleaned_data[u'Wkład 15%'] = 0.15 * cleaned_data['Cena mieszkania + parking MDM']
cleaned_data[u'Wkład 20%'] = 0.2 * cleaned_data['Cena mieszkania + parking MDM']

cleaned_data[u'latlong'] = zip(cleaned_data[u'Szerokość geograficzna'], cleaned_data[u'Długosć geograficzna'])

gps_points = list(cleaned_data['latlong'].unique())

gmaps = googlemaps.Client(key=client_key)


def to_minutes(seconds):
    return math.ceil(seconds / 60.0)


def get_duration(result):
    leg = result[0]['legs'][0]
    if 'duration_in_traffic' in leg:
        return to_minutes(leg['duration_in_traffic']['value'])
    return to_minutes(leg['duration']['value'])


def get_data_for_gps_data(gps_data):
    try:
        high_traffic = gmaps.directions(gps_data, target_location, mode="driving",
                                        departure_time=high_traffic_date)
        low_traffic = gmaps.directions(gps_data, target_location, mode="driving",
                                       departure_time=low_traffic_date)
        weekday = gmaps.directions(gps_data, target_location, mode="driving",
                                   departure_time=weekend_midday_date)
        cycling = gmaps.directions(gps_data, target_location, mode="bicycling",
                                   departure_time=high_traffic_date)

        return {
            'latlong': gps_data,
            'Czas dojazdu samochodem w korkach': get_duration(high_traffic),
            u'Czas dojazdu samochodem bez korków': get_duration(low_traffic),
            u'Czas dojazdu samochodem w weekend': get_duration(weekday),
            u'Czas dojazdu rowerem': get_duration(cycling)
        }
    except googlemaps.exceptions.TransportError:
        return gps_data


pool = Pool(7)

travel_data = []
while gps_points:
    print "Fetching %s gps points" % len(gps_points)
    results = pool.map(get_data_for_gps_data, gps_points)
    travel_data += [result for result in results if isinstance(result, dict)]
    gps_points = [result for result in results if isinstance(result, tuple)]

travel_data = pandas.DataFrame(travel_data)
cleaned_data = cleaned_data.merge(travel_data, on='latlong')
cleaned_data = cleaned_data.drop('latlong', 1)

with open("/home/ppastuszka/Dokumenty/cleanedapartmentdata.csv", "wb") as f:
    cleaned_data.to_csv(f, encoding='utf-8')

cleaned_data.to_pickle("/home/ppastuszka/Dokumenty/cleanedapartmentdata.pkl")
