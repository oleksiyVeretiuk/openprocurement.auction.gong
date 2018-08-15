# -*- coding: utf-8 -*-

tender_data = {u'data': {u'auctionPeriod': {u'endDate': None,
    u'startDate': u'2017-07-03T17:32:05.661358+03:00'},
    u'bids': [{u'date': u'2014-11-19T08:22:21.726234+00:00',
        u'id': u'd3ba84c66c9e4f34bfb33cc3c686f137',
        u'value': {u'amount': 475000.0,
            u'currency': None,
            u'valueAddedTaxIncluded': True}},
        {u'date': u'2014-11-19T08:22:24.038426+00:00',
            u'id': u'5675acc9232942e8940a034994ad883e',
            u'value': {u'amount': 480000.0,
                u'currency': None,
                u'valueAddedTaxIncluded': True}}],
            u'dateModified': u'2014-11-19T08:22:24.866669+00:00',
            u'description': u'Tender Description',
            u'items': [{u'additionalClassifications': [{u'description': u'\u041f\u043e\u0441\u043b\u0443\u0433\u0438 \u0448\u043a\u0456\u043b\u044c\u043d\u0438\u0445 \u0457\u0434\u0430\u043b\u0435\u043d\u044c',
                u'id': u'55.51.10.300',
                u'scheme': u'\u0414\u041a\u041f\u041f'}],
                u'classification': {u'description': u'\u041f\u043e\u0441\u043b\u0443\u0433\u0438 \u0437 \u0445\u0430\u0440\u0447\u0443\u0432\u0430\u043d\u043d\u044f \u0443 \u0448\u043a\u043e\u043b\u0430\u0445',
                    u'id': u'55523100-3',
                    u'scheme': u'CPV'},
                u'description': u'\u041f\u043e\u0441\u043b\u0443\u0433\u0438 \u0448\u043a\u0456\u043b\u044c\u043d\u0438\u0445 \u0457\u0434\u0430\u043b\u0435\u043d\u044c',
                u'quantity': 5,
                u'unit': {u'name': u'item'}}],
            u'minimalStep': {u'amount': 35000.0,
                u'currency': u'UAH',
                u'valueAddedTaxIncluded': True},
            u'procurementMethodType': u'belowThreshold',
            u'procuringEntity': {u'address': {u'countryName': u'\u0423\u043a\u0440\u0430\u0457\u043d\u0430',
                u'locality': u'\u043c. \u0412\u0456\u043d\u043d\u0438\u0446\u044f',
                u'postalCode': u'21027',
                u'region': u'\u043c. \u0412\u0456\u043d\u043d\u0438\u0446\u044f',
                u'streetAddress': u'\u0432\u0443\u043b. \u0421\u0442\u0430\u0445\u0443\u0440\u0441\u044c\u043a\u043e\u0433\u043e. 22'},
                u'identifier': {u'id': u'21725150',
                    u'legalName': u'\u0417\u0430\u043a\u043b\u0430\u0434 "\u0417\u0430\u0433\u0430\u043b\u044c\u043d\u043e\u043e\u0441\u0432\u0456\u0442\u043d\u044f \u0448\u043a\u043e\u043b\u0430 \u0406-\u0406\u0406\u0406 \u0441\u0442\u0443\u043f\u0435\u043d\u0456\u0432 \u2116 10 \u0412\u0456\u043d\u043d\u0438\u0446\u044c\u043a\u043e\u0457 \u043c\u0456\u0441\u044c\u043a\u043e\u0457 \u0440\u0430\u0434\u0438"',
                    u'scheme': u'https://ns.openprocurement.org/ua/edrpou',
                    u'uri': u'http://sch10.edu.vn.ua/'},
                u'name': u'\u0417\u041e\u0421\u0428 #10 \u043c.\u0412\u0456\u043d\u043d\u0438\u0446\u0456'},
            u'auctionID': u'UA-11111',
            u'title': u'Tender Title',
            u'value': {u'amount': 500000.0,
                u'currency': u'UAH',
                u'valueAddedTaxIncluded': True}}}


test_organization = {
                    "name": u"Державне управління справами",
                    "identifier": {
                        "scheme": u"UA-EDR",
                        "id": u"00037256",
                        "uri": u"http://www.dus.gov.ua/"
                        },
                    "address": {
                        "countryName": u"Україна",
                        "postalCode": u"01220",
                        "region": u"м. Київ",
                        "locality": u"м. Київ",
                        "streetAddress": u"вул. Банкова, 11, корпус 1"
                        },
                    "contactPoint": {
                        "name": u"Державне управління справами",
                        "telephone": u"0440000000"
                        }
                    }


test_auction_document = {
    'current_stage': 2,
    'stages': [
        {
            "start": "2017-07-14T11:05:46+03:00",
            "type": "pause",
            "stage": "pause"
        },
        {
            "bidder_id": "5675acc9232942e8940a034994ad883e",
            "label": {
                "ru": "Участник №1",
                "en": "Bidder #1",
                "uk": "Учасник №1"
            },
            "start": "2017-07-14T11:10:46+03:00",
            "amount": 259500,
            "time": "2017-07-12T11:36:23.148237+03:00",
            "type": "bids"
        },
        {
            "bidder_id": "f7c8cd1d56624477af8dc3aa9c4b3ea3",
            "label": {
                "ru": "Участник №2",
                "en": "Bidder #2",
                "uk": "Учасник №2"
            },
            "start": "2017-07-14T11:12:46+03:00",
            "amount": 258500,
            "time": "2017-07-12T13:56:44.366383+03:00",
            "type": "bids"
        }
    ],
    "minimalStep": {
        "currency": "UAH",
        "amount": 7500,
        "valueAddedTaxIncluded": True
    }
}
