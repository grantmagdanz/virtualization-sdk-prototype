#
# Copyright (c) 2019 by Delphix. All rights reserved.
#

import os

__path__ = __import__("pkgutil").extend_path(__path__, __name__)

file_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(file_dir, 'VERSION')) as f:
    __version__ = f.read().strip()
