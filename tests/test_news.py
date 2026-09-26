import sys,unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import news
NOW=datetime(2026,9,26,12,tzinfo=timezone.utc)
RSS=b'''<?xml version="1.0"?><rss><channel>
<item><title>NVIDIA opens AI lab in Abu Dhabi</title><link>https://www.example-news.com/a</link><pubDate>Fri, 25 Sep 2026 08:00:00 GMT</pubDate></item>
<item><title>Football results</title><link>https://www.example-news.com/b</link><pubDate>Fri, 25 Sep 2026 09:00:00 GMT</pubDate></item>
<item><title>AI &amp; chips &lt;b&gt;update&lt;/b&gt;</title><link>https://evil.example/c</link><pubDate>Fri, 25 Sep 2026 10:00:00 GMT</pubDate></item>
<item><title>Old AI story</title><link>https://www.example-news.com/d</link><pubDate>Mon, 01 Jun 2026 10:00:00 GMT</pubDate></item>
</channel></rss>'''
ATOM=b'''<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><title>&#1575;&#1604;&#1584;&#1603;&#1575;&#1569; &#1575;&#1604;&#1575;&#1589;&#1591;&#1606;&#1575;&#1593;&#1610; &#1601;&#1610; &#1583;&#1576;&#1610;</title><link rel="alternate" href="https://ar.example-news.com/x"/><updated>2026-09-26T06:00:00Z</updated></entry></feed>'''
SRC={'id':'ex','feed':'https://www.example-news.com/rss','homepage':'https://www.example-news.com/','link_hosts':['www.example-news.com'],'lang':'en','region':'global','ai_only':False}
class NewsTests(unittest.TestCase):
    def test_rss_filtering_and_domain_boundary(self):
        with mock.patch.object(news,'fetch',return_value=RSS):items=news.collect(SRC,NOW)
        self.assertEqual([i['title'] for i in items],['NVIDIA opens AI lab in Abu Dhabi'])
        self.assertTrue(items[0]['uae'])
    def test_atom_arabic(self):
        src={**SRC,'id':'ar','homepage':'https://ar.example-news.com/','link_hosts':[],'lang':'ar'}
        with mock.patch.object(news,'fetch',return_value=ATOM):items=news.collect(src,NOW)
        self.assertEqual(len(items),1);self.assertTrue(items[0]['uae']);self.assertEqual(items[0]['lang'],'ar')
    def test_allowed(self):
        self.assertTrue(news.allowed('https://sub.example-news.com/x',SRC))
        for u in ['http://www.example-news.com/x','https://example-news.com.evil.io/x','https://a@example-news.com/x']:self.assertFalse(news.allowed(u,SRC))
    def test_clean_strips_markup(self):self.assertEqual(news.clean('AI &amp; <b>chips</b>\n now'),'AI & chips now')
if __name__=='__main__':unittest.main()
