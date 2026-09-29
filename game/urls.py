from django.urls import path

from . import staff_views, views

app_name = 'game'

urlpatterns = [
    path('', views.home, name='home'),
    path('start', views.start, name='start'),
    path('play', views.play, name='play'),
    path('play/command', views.command, name='command'),
    path('play/state', views.state, name='state'),
    path('done', views.done, name='done'),
    path('staff', staff_views.lookup, name='staff_lookup'),
    path('staff/prize', staff_views.give_prize, name='staff_prize'),
]
