import unittest


class TestWorkWithResultUtils(unittest.TestCase):
    pass


class TestCustomContextManagers(unittest.TestCase):
    pass


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestWorkWithResultUtils))
    suite.addTest(unittest.makeSuite(TestCustomContextManagers))

    return suite
