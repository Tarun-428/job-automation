import pytest
from agents.job_parser import JobParserAgent
from unittest.mock import MagicMock


@pytest.fixture
def parser():
    return JobParserAgent(ai_router=MagicMock())


def test_detect_linkedin(parser):
    assert parser.detect_platform("https://www.linkedin.com/jobs/view/123456") == "linkedin"


def test_detect_greenhouse(parser):
    assert parser.detect_platform("https://boards.greenhouse.io/company/jobs/789") == "greenhouse"


def test_detect_lever(parser):
    assert parser.detect_platform("https://jobs.lever.co/company/job-id") == "lever"


def test_detect_custom(parser):
    assert parser.detect_platform("https://careers.somecompany.com/apply") == "custom"


def test_detect_workday(parser):
    assert parser.detect_platform("https://company.wd1.myworkdayjobs.com/en-US/External") == "workday"
