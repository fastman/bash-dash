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
    path('staff/hall', staff_views.hall, name='staff_hall'),
    path('staff/hall/board', staff_views.hall_board, name='staff_hall_board'),
    path('staff/prize', staff_views.give_prize, name='staff_prize'),
]
