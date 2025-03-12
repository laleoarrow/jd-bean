#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import random
import re
from pathlib import Path
from loguru import logger
import requests
from dotenv import load_dotenv

class JDBeans:
    def __init__(self):
        self.session = requests.Session()
        self.cookies = {}
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'sec-ch-ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Microsoft Edge";v="122"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site'
        }
        # 确保日志等级
        logger.remove()
        logger.add(lambda msg: print(msg, end=""), level="INFO")
        logger.add("jd_beans.log", rotation="10 MB", level="DEBUG", encoding="utf-8")
    
    def parse_cookie_table(self, cookie_text):
        """解析从开发者工具复制的cookie表格"""
        try:
            cookies = {}
            lines = cookie_text.strip().split('\n')
            
            for line in lines:
                parts = line.strip().split('\t')
                if len(parts) >= 2:
                    name = parts[0].strip()
                    value = parts[1].strip()
                    
                    # 过滤掉空值和长度为0的cookie
                    if name and value and len(value) > 0:
                        cookies[name] = value
            
            if not cookies:
                logger.error("未找到有效的京东cookies")
                return None
                
            # 检查关键cookie，但不硬性要求
            required_cookies = ['pt_key', 'pt_pin']
            missing = [c for c in required_cookies if c not in cookies]
            
            # 如果缺少pt_key和pt_pin，但有其他cookie，仍然继续尝试
            if missing:
                logger.warning(f"缺少关键cookie: {missing}，但将继续尝试使用现有cookie")
            
            return cookies
        except Exception as e:
            logger.error(f"解析cookie表格失败: {str(e)}")
            return None
    
    def set_cookies(self, cookie_input):
        """设置cookies，支持多种格式"""
        try:
            # 如果输入是文件路径，则从文件读取
            if os.path.exists(cookie_input):
                with open(cookie_input, 'r', encoding='utf-8') as f:
                    cookie_text = f.read()
            else:
                cookie_text = cookie_input
            
            # 首先尝试解析为表格格式
            if '\t' in cookie_text:
                parsed_cookies = self.parse_cookie_table(cookie_text)
                if parsed_cookies:
                    self.cookies = parsed_cookies
                else:
                    return False
            else:
                # 尝试解析为字符串格式
                cookie_pairs = cookie_text.split(';')
                self.cookies = {}
                for pair in cookie_pairs:
                    if '=' in pair:
                        name, value = pair.strip().split('=', 1)
                        name = name.strip()
                        value = value.strip()
                        if name and value:
                            self.cookies[name] = value
            
            # 保存cookies到文件
            with open('jd_cookies.json', 'w', encoding='utf-8') as f:
                json.dump(self.cookies, f, ensure_ascii=False, indent=2)
            
            logger.success(f"成功设置 {len(self.cookies)} 个cookies!")
            return True
        except Exception as e:
            logger.error(f"设置cookies失败: {str(e)}")
            return False
    
    def load_cookies(self):
        """从文件加载cookies"""
        try:
            if os.path.exists('jd_cookies.json'):
                with open('jd_cookies.json', 'r', encoding='utf-8') as f:
                    self.cookies = json.load(f)
                logger.success(f"从文件加载了 {len(self.cookies)} 个cookies")
                return True
        except Exception as e:
            logger.error(f"加载cookies失败: {str(e)}")
        return False
    
    def _update_session_cookies(self):
        """更新session的cookies"""
        # 先清除所有cookies，防止旧cookie影响
        self.session.cookies.clear()
        # 然后更新cookies
        for name, value in self.cookies.items():
            self.session.cookies.set(name, value, domain=".jd.com")
    
    def check_login_status(self):
        """检查登录状态"""
        try:
            # 更新session的cookies
            self._update_session_cookies()
            
            # 尝试多种方法检查登录状态
            
            # 方法1: 访问个人主页检查
            headers = {
                **self.headers,
                'Referer': 'https://home.m.jd.com/',
                'Origin': 'https://home.m.jd.com'
            }
            
            # 先尝试京豆查询接口
            bean_url = "https://api.m.jd.com/client.action"
            bean_data = {
                "functionId": "queryBeanIndex",
                "appid": "ld",
                "body": "{}"
            }
            bean_headers = {
                **self.headers,
                'Referer': 'https://bean.m.jd.com/',
                'Origin': 'https://bean.m.jd.com'
            }
            
            try:
                bean_resp = self.session.post(
                    bean_url,
                    data=bean_data,
                    headers=bean_headers
                )
                
                # 尝试解析响应
                result = bean_resp.json()
                logger.debug(f"京豆查询响应: {result}")
                
                # 如果能获取到京豆数量，或者返回了有效的数据结构，就认为登录成功
                if "data" in result:
                    if "jingBean" in result["data"]:
                        bean_count = result["data"]["jingBean"]
                        logger.success(f"登录状态正常，当前京豆数量: {bean_count}")
                    else:
                        logger.success("登录状态正常，但未获取到京豆数量")
                    return True
            except Exception as e:
                logger.debug(f"京豆查询失败: {str(e)}")
            
            # 如果上面的方法失败，尝试访问个人主页
            try:
                response = self.session.get(
                    'https://home.m.jd.com/myJd/newhome.action',
                    headers=headers,
                    allow_redirects=False  # 不跟随重定向，可以更准确判断登录状态
                )
                
                # 如果状态码是200且没有被重定向到登录页
                if response.status_code == 200 and "用户未登录" not in response.text:
                    logger.success("访问个人主页成功，登录状态正常")
                    return True
            except Exception as e:
                logger.debug(f"访问个人主页失败: {str(e)}")
            
            # 最后尝试通用的登录检查接口
            try:
                islogin_url = 'https://plogin.m.jd.com/cgi-bin/ml/islogin'
                islogin_headers = {
                    **self.headers,
                    'Referer': 'https://h5.m.jd.com/',
                    'Origin': 'https://h5.m.jd.com'
                }
                islogin_resp = self.session.get(
                    islogin_url, 
                    headers=islogin_headers
                )
                
                if islogin_resp.status_code == 200:
                    result = islogin_resp.json()
                    if result.get('islogin') == '1':
                        logger.success("登录检查接口返回登录状态正常")
                        return True
            except Exception as e:
                logger.debug(f"登录检查接口调用失败: {str(e)}")
            
            # 尝试了所有方法都失败，才判定为登录失败
            logger.warning("所有登录状态检查方法均失败，可能未登录")
            return False
        except Exception as e:
            logger.error(f"检查登录状态失败: {str(e)}")
            return False
    
    def sign_beans(self):
        """
        执行签到
        """
        max_retries = 3
        retry_delay = [3, 5, 8]  # 重试延迟时间（秒）
        
        # 更新session的cookies
        self._update_session_cookies()
        
        for attempt in range(max_retries):
            try:
                # 准备签到所需的headers
                headers = {
                    **self.headers,
                    'Referer': 'https://bean.m.jd.com/',
                    'Origin': 'https://bean.m.jd.com'
                }
                
                # 1. 访问京豆首页
                logger.info("访问京豆首页...")
                index_url = 'https://bean.m.jd.com/bean/signIndex.action'
                response = self.session.get(
                    index_url,
                    headers=headers
                )
                logger.debug(f"首页响应状态码: {response.status_code}")
                time.sleep(random.uniform(1, 2))
                
                # 2. 获取签到状态
                logger.info("获取签到状态...")
                status_url = "https://api.m.jd.com/client.action"
                status_data = {
                    "functionId": "queryBeanIndex",
                    "appid": "ld",
                    "body": "{}"
                }
                response = self.session.post(
                    status_url,
                    data=status_data,
                    headers=headers
                )
                status_result = None
                try:
                    status_result = response.json()
                    logger.debug(f"状态检查响应: {status_result}")
                    
                    # 检查是否已签到
                    if status_result.get("data", {}).get("dailyAward", {}).get("beanAward", {}).get("beanCount"):
                        logger.success(f"今日已签到，获得 {status_result['data']['dailyAward']['beanAward']['beanCount']} 京豆")
                        return status_result
                except Exception as e:
                    logger.warning(f"解析签到状态失败: {str(e)}")
                
                time.sleep(random.uniform(1, 2))
                
                # 尝试简化的签到请求
                logger.info("尝试简化签到...")
                simple_sign_url = "https://api.m.jd.com/client.action?functionId=signBeanIndex&appid=ld"
                response = self.session.get(
                    simple_sign_url,
                    headers=headers
                )
                logger.debug(f"简化签到响应状态码: {response.status_code}")
                time.sleep(1)
                
                # 3. 执行标准签到
                logger.info("执行标准签到...")
                sign_url = "https://api.m.jd.com/client.action"
                sign_params = {
                    "functionId": "signBeanIndex",
                    "appid": "ld",
                    "body": "{}"
                }
                sign_headers = {
                    **headers,
                    'Content-Type': 'application/x-www-form-urlencoded',
                }
                response = self.session.post(
                    sign_url,
                    data=sign_params,
                    headers=sign_headers
                )
                
                # 尝试解析结果
                try:
                    result = response.json()
                    logger.info(f"签到结果: {result}")
                    
                    # 检查是否签到成功
                    if result.get("code") == "0" and result.get("data"):
                        if result["data"].get("dailyAward"):
                            bean_count = result["data"]["dailyAward"].get("beanAward", {}).get("beanCount", 0)
                            logger.success(f"签到成功，获得 {bean_count} 京豆!")
                            return result
                        elif result["data"].get("continuityAward"):
                            bean_count = result["data"]["continuityAward"].get("beanAward", {}).get("beanCount", 0)
                            logger.success(f"连续签到成功，获得 {bean_count} 京豆!")
                            return result
                        else:
                            logger.success("签到成功!")
                            return result
                    
                    # 处理常见错误
                    if result.get("code") == "3" and "用户未登录" in str(result):
                        logger.error("签到失败：用户未登录，请重新获取cookies")
                        break
                        
                    if result.get("code") == "402":
                        if attempt < max_retries - 1:
                            delay = retry_delay[attempt]
                            logger.warning(f"签到请求被限制，{delay}秒后重试...")
                            time.sleep(delay)
                            continue
                    
                    if "errorMessage" in result:
                        logger.warning(f"签到失败，返回信息: {result['errorMessage']}")
                        
                    # 如果还没成功，尝试备用签到方法
                    if attempt == max_retries - 1:
                        logger.info("尝试备用签到方法...")
                        return self._fallback_sign()
                        
                    return result
                    
                except Exception as e:
                    logger.error(f"解析签到结果失败: {str(e)}")
                    if attempt < max_retries - 1:
                        delay = retry_delay[attempt]
                        logger.warning(f"发生错误，{delay}秒后重试...")
                        time.sleep(delay)
                    else:
                        # 最后一次尝试备用方法
                        return self._fallback_sign()
                
            except Exception as e:
                logger.error(f"签到过程出错: {str(e)}")
                if attempt < max_retries - 1:
                    delay = retry_delay[attempt]
                    logger.warning(f"发生错误，{delay}秒后重试...")
                    time.sleep(delay)
                else:
                    # 最后一次尝试备用方法
                    return self._fallback_sign()
        
        return None
    
    def _fallback_sign(self):
        """备用签到方法"""
        try:
            logger.info("使用备用方法签到...")
            
            # 使用不同的签到接口
            headers = {
                **self.headers,
                'Referer': 'https://bean.m.jd.com/',
                'Origin': 'https://bean.m.jd.com'
            }
            
            # 先访问签到页面
            self.session.get(
                'https://bean.m.jd.com/bean/signIndex.action',
                headers=headers
            )
            time.sleep(random.uniform(1, 2))
            
            # 执行签到
            sign_url = "https://api.m.jd.com/client.action"
            sign_data = {
                "functionId": "signBeanAct",
                "appid": "ld",
                "body": '{"fp":"-","shshshfp":"-","shshshfpa":"-","referUrl":"-","userAgent":"-","jda":"-"}'
            }
            response = self.session.post(
                sign_url,
                data=sign_data,
                headers=headers
            )
            
            try:
                result = response.json()
                logger.info(f"备用签到结果: {result}")
                
                if result.get("code") == "0" or "签到成功" in str(result):
                    logger.success("备用方法签到成功!")
                elif "已签到" in str(result) or "今天已经签到" in str(result):
                    logger.success("今日已签到!")
                return result
            except:
                logger.warning(f"备用签到返回格式异常: {response.text[:100]}")
                return None
        except Exception as e:
            logger.error(f"备用签到失败: {str(e)}")
            return None

    def print_cookie_help(self):
        """打印获取cookie的帮助信息"""
        help_text = """
如何获取京东Cookie：

1. 使用Edge浏览器打开京东网站(www.jd.com)并登录
2. 登录成功后，按F12打开开发者工具
3. 在开发者工具中：
   - 点击顶部的"应用程序"(Application)标签
   - 在左侧找到 Cookies -> https://www.jd.com
   - 在右侧表格中全选所有内容（Ctrl+A）并复制（Ctrl+C）
   - 粘贴到 cookies.txt 文件中

注意：
1. 确保已经登录京东网站，且能在表格中看到多行cookie数据
2. 如果登录失败，请尝试重新登录京东网站，然后重新获取cookies
3. 建议在获取cookies之前先清除浏览器缓存
4. 确保复制的cookie包含pt_key和pt_pin（如果有的话）
"""
        print(help_text)
    
    def run(self):
        """运行主程序"""
        if not self.load_cookies():
            logger.info("需要设置cookies")
            self.print_cookie_help()
            
            # 检查是否存在cookies.txt文件
            if os.path.exists('cookies.txt'):
                logger.info("检测到cookies.txt文件，正在读取...")
                if not self.set_cookies('cookies.txt'):
                    return
            else:
                logger.error("未找到cookies.txt文件，请按照说明创建文件")
                return
        
        if self.check_login_status():
            result = self.sign_beans()
            if result:
                logger.info("签到流程完成")
            else:
                logger.warning("签到可能未成功，请检查日志")
        else:
            logger.error("登录状态检查失败，请重新设置cookies")
            # 删除旧的cookie文件，以便下次重新获取
            if os.path.exists('jd_cookies.json'):
                os.remove('jd_cookies.json')
            self.print_cookie_help()

def main():
    jd = JDBeans()
    jd.run()

if __name__ == '__main__':
    main()
