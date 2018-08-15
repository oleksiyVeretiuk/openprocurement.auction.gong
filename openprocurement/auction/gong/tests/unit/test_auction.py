import unittest
import pytest


@pytest.mark.usefixtures("auction")
class TestAuctionObject(unittest.TestCase):
    pass


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestAuctionObject))

    return suite
