import unittest


class TestFlaskApplication(unittest.TestCase):
    pass


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestFlaskApplication))

    return suite
