import requests
import re
import json
import time
import logging
from urllib.parse import unquote, urlparse
import cloudscraper

logger = logging.getLogger(__name__)

class TeraboxDownloader:
    def __init__(self):
        # Use cloudscraper to bypass Cloudflare
        self.scraper = cloudscraper.create_scraper()
        self.scraper.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
        })
    
    def extract_info(self, url):
        """Extract file information from Terabox URL"""
        try:
            logger.info(f"Processing URL: {url}")
            
            # Normalize URL
            if '1024terabox.com' in url:
                url = url.replace('1024terabox.com', 'terabox.com')
            
            # Fetch the page
            response = self.scraper.get(url, timeout=30)
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch page: {response.status_code}")
                return None
            
            html = response.text
            
            # Method 1: Try to find JSON data
            json_pattern = r'window\.data\s*=\s*({.*?});'
            match = re.search(json_pattern, html, re.DOTALL)
            
            if match:
                try:
                    data = json.loads(match.group(1))
                    if 'file' in data and 'filename' in data['file']:
                        return {
                            'filename': unquote(data['file']['filename']),
                            'size': data['file'].get('size', 0),
                            'direct_url': data['file'].get('download_url')
                        }
                except:
                    pass
            
            # Method 2: Try to find meta tags
            meta_patterns = {
                'filename': r'<meta\s+property="og:title"\s+content="([^"]+)"',
                'url': r'<meta\s+property="og:url"\s+content="([^"]+)"',
                'type': r'<meta\s+property="og:type"\s+content="([^"]+)"',
            }
            
            info = {}
            for key, pattern in meta_patterns.items():
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    info[key] = unquote(match.group(1))
            
            # Method 3: Look for video tags
            video_pattern = r'<video[^>]+src="([^"]+)"'
            match = re.search(video_pattern, html, re.IGNORECASE)
            if match:
                info['direct_url'] = match.group(1)
            
            # Method 4: Look for download button
            download_pattern = r'<a[^>]+href="([^"]+)"[^>]*download[^>]*>'
            match = re.search(download_pattern, html, re.IGNORECASE)
            if match:
                info['direct_url'] = match.group(1)
            
            # If we have some info, return it
            if info:
                if 'filename' not in info:
                    # Extract filename from URL
                    parsed = urlparse(url)
                    path = parsed.path
                    if '/' in path:
                        filename = path.split('/')[-1]
                        if filename:
                            info['filename'] = unquote(filename)
                
                return info
            
            # Method 5: Try to find title
            title_pattern = r'<title>([^<]+)</title>'
            match = re.search(title_pattern, html, re.IGNORECASE)
            if match:
                title = match.group(1).strip()
                if ' - ' in title:
                    filename = title.split(' - ')[0].strip()
                    return {
                        'filename': filename,
                        'source': 'title'
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting info: {str(e)}")
            return None
    
    def get_direct_download(self, url):
        """Get direct download link using alternative methods"""
        try:
            info = self.extract_info(url)
            if not info:
                return None
            
            # If we have direct URL, return it
            if 'direct_url' in info:
                return {
                    'filename': info.get('filename', f'file_{int(time.time())}'),
                    'url': info['direct_url']
                }
            
            # Try to construct download URL from share URL
            # Terabox pattern: https://terabox.com/s/XXXXX
            if '/s/' in url:
                # Try to get file ID
                parts = url.split('/s/')
                if len(parts) > 1:
                    file_id = parts[1].split('?')[0].split('/')[0]
                    # Try direct API endpoint (may not work)
                    direct_url = f"https://www.terabox.com/api/file/download?fid={file_id}"
                    
                    return {
                        'filename': info.get('filename', f'file_{int(time.time())}'),
                        'url': direct_url,
                        'file_id': file_id
                    }
            
            return {
                'filename': info.get('filename', f'file_{int(time.time())}'),
                'original_url': url
            }
            
        except Exception as e:
            logger.error(f"Error getting direct download: {str(e)}")
            return None
    
    def is_terabox_url(self, url):
        """Check if URL is from Terabox"""
        terabox_domains = [
            'terabox.com',
            '1024terabox.com',
            'terabox.app',
            'www.terabox.com',
            'dubox.com',
            'www.dubox.com'
        ]
        return any(domain in url.lower() for domain in terabox_domains)
    
    def download_file(self, url, save_path):
        """Download file directly"""
        try:
            response = self.scraper.get(url, stream=True, timeout=60)
            
            if response.status_code == 200:
                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                return True
            else:
                logger.error(f"Download failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            return False
