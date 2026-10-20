
[app]

title = TAKWEED Customer Coding
package.name = takweedcustomercoding
package.domain = com.mohamedselim

source.dir = .
source.include_exts = py,kv,png,jpg,jpeg,json,txt,ttf

version = 1.0.0

requirements = python3==3.13.7,hostpython3==3.13.7,kivy==2.3.1,requests,certifi,plyer

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION

android.api = 35
android.minapi = 24
android.ndk = 27c
android.ndk_api = 24
android.archs = arm64-v8a

p4a.branch = develop
