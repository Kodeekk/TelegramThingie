import unittest
from src.utils.logger import Logger, logger

def log_globally():
    return logger.format_info("test")

class TestUtils(unittest.TestCase):
    def test_logger_context(self):
        class TestClass:
            def get_log(self):
                return logger.format_info("test")
        
        self.assertEqual(TestClass().get_log(), "[TestClass] INFO: test")
        self.assertEqual(logger.format_info("test"), "[TestUtils] INFO: test")
        self.assertEqual(log_globally(), "[App] INFO: test")

    def test_logger_levels(self):
        import io
        from contextlib import redirect_stdout
        
        logger.set_level("PROD")
        f = io.StringIO()
        with redirect_stdout(f):
            logger.debug("should not see this")
            logger.info("should see this")
        
        output = f.getvalue()
        self.assertNotIn("DEBUG: should not see this", output)
        self.assertIn("INFO: should see this", output)

        logger.set_level("DEV")
        f = io.StringIO()
        with redirect_stdout(f):
            logger.debug("now should see this")
        
        output = f.getvalue()
        self.assertIn("DEBUG: now should see this", output)