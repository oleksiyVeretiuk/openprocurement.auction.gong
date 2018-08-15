import unittest


class TestDBServiceMixin(unittest.TestCase):
    pass


class TestBiddersServiceMixin(unittest.TestCase):
    pass


class TestAuctionAPIServiceMixin(unittest.TestCase):
    pass


class TestStagesServiceMixin(unittest.TestCase):
    pass


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestDBServiceMixin))
    suite.addTest(unittest.makeSuite(TestBiddersServiceMixin))
    suite.addTest(unittest.makeSuite(TestAuctionAPIServiceMixin))
    suite.addTest(unittest.makeSuite(TestStagesServiceMixin))

    return suite
