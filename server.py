import webbrowser
import os
from threading import Timer
from waitress import serve
from app import server

# import sklearn.__check_build._check_build
# import sklearn.metrics._pairwise_distances_reduction._datasets_pair
# import sklearn.metrics._pairwise_distances_reduction._middle_term_computer
# import sklearn.metrics

port = 8080


def open_browser():
    webbrowser.open_new("http://localhost:%d" % port)


Timer(1, open_browser).start()
serve(server)
