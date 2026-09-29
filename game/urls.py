from django.urls import path

from . import views

app_name = 'game'

urlpatterns = [
    path('', views.home, name='home'),
    path('start', views.start, name='start'),
    path('play', views.play, name='play'),
    path('play/command', views.command, name='command'),
    path('done', views.done, name='done'),
]
