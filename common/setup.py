import setuptools

PYTHON_SRC = 'src/main/python'

install_requires = [
  "protobuf ==3.6.1",
]

setuptools.setup(name='dvp-common',
                 version='1.0.1-internal-002',
                 install_requires=install_requires,
                 package_dir={'': PYTHON_SRC},
                 packages=setuptools.find_packages(PYTHON_SRC),
)
