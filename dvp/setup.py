import setuptools

PYTHON_SRC = 'src/main/python'

install_requires = [
  "dvp-common == 1.0.1-internal-002",
  "dvp-libs == 1.0.1-internal-002",
  "dvp-platform == 1.0.1-internal-002",
  "dvp-tools == 1.0.1-internal-002",
]

setuptools.setup(name='dvp',
                 version='1.0.1-internal-002',
                 install_requires=install_requires,
                 package_dir={'': PYTHON_SRC},
                 packages=setuptools.find_packages(PYTHON_SRC),
)
