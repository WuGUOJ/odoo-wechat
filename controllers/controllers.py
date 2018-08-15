# -*- coding: utf-8 -*-
from werkzeug.urls import url_encode
from werkzeug.exceptions import BadRequest

from odoo import api, http, SUPERUSER_ID, _
from odoo.http import request
from odoo.addons.auth_oauth.controllers.main import OAuthLogin as Home, OAuthController as Controller

import requests

APPID = 'xxx'  # 你的微信APPID
APPSECRET = 'xxx'  # 你的微信APPSECRET


class OAuthLogin(Home):
    def list_providers(self):
        # 获取所有的OAuth服务商
        providers = super(OAuthLogin, self).list_providers()
        for provider in providers:
            # provider['auth_endpoint']获取的就是身份验证网址
            # 服务商的相关字段信息可以在数据库结构中搜索模型auth就可以找到了
            if 'weixin' in provider['auth_endpoint']:
                # 构造微信请求参数
                params = dict(
                    response_type='code',
                    appid=APPID,  # 你也可以通过provider['client_id']获得，前提是你在界面配置过
                    redirect_uri='http://你的域名/wechat/',  # 微信回调处理url，后面的wechat是我自己添加的，可改
                    scope=provider['scope'],
                    state=str(provider['id'])  # 我这里把服务商id放在这个参数中
                )
                # 最终的微信登入请求链接
                provider['auth_link'] = "{}?{}#wechat_redirect".format(provider['auth_endpoint'], url_encode(params))
        return providers


class OAuthController(Controller):
    @http.route('/wechat/', type='http', auth='none')
    def login(self, **kwargs):
        # OAuth提供商id
        provider_id = kwargs.get('state', '')
        
        # 以下微信相关 #
        code = kwargs.get('code', '')
        # code换取token
        token_info = self.get_token(code)
        openid = token_info['openid']
        # 换取用户信息
        user_info = self.get_userinfo(token_info['access_token'], openid)
        
        print(user_info)
        city = user_info['province'] + " " + user_info['city']
        # 验证核心函数，返回数据库中用户id
        uid = request.session.authenticate(request.session.db, user_info['nickname'], user_info['openid'])
        if uid is False:
            # 以超级管理员创建用户
            request.env['res.users'].sudo().create({
                "login": user_info['nickname'],  # 登入名，可重复
                "password": user_info['openid'],  # 我这里把openID当做密码
                "name": user_info['nickname'],   # 用户名，不可重复
                "oauth_provider_id": provider_id,  # 服务商id，可选
                "city": city,  # 可选，还可添加其他参数，这里就不列举了
                # 将该用户添加到门户组, 如果是员工登入就不设置"groups_id"
                "groups_id": request.env.ref('base.group_portal'),
            })
            # 待解决：因为新用户第一次验证不成功，第二次再扫的时候就可以，
            # 所以我这里跳转到重新登入，希望大神解决这个问题
            return http.local_redirect('/web/login')
        return http.local_redirect('/')

    def get_token(self, code):
        # 链接的第一行也可以在你配置的界面中获取，我是直接写在这里
        url = "https://api.weixin.qq.com/sns/oauth2/access_token?" \
              "appid={}&secret={}&code={}&grant_type=authorization_code".format(APPID, APPSECRET, code)
        return self.get_result(url)

    def get_userinfo(self, token, openid):
        url = "https://api.weixin.qq.com/sns/userinfo?access_token={}&openid={}".format(token, openid)
        return self.get_result(url)

    @staticmethod
    def get_result(url):
        res = requests.get(url)
        res.encoding = res.apparent_encoding
        result = res.json()
        if 'errcode' not in result:
            # 返回字典类型数据
            return result
        else:
            raise BadRequest(res['errmsg'])

