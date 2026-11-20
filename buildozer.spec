[app]
title = Roblox Checker
package.name = robloxchecker
package.domain = com.peeeeter05
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0

requirements = python3,kivy,curl_cffi,pyjnius,openssl,plyer,requests,urllib3,certifi,charset-normalizer,idna

orientation = portrait
android.permissions = INTERNET, READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE
android.api = 31
android.minapi = 21

[buildozer]
log_level = 2
warn_on_root = 1
