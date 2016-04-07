from setuptools import setup, find_packages

setup(name='pdf-diff',
      version='1.0',
      description='Finds differences between two PDF documents',
      url='https://github.com/JoshData/pdf-diff',
      author='JoshData',
      author_email='',
      license='CC0 1.0 Universal',
      packages=find_packages(),
      install_requires=[
          'diff_match_patch_python',
          'lxml',
          'pillow',
      ],
      entry_points = {
        'console_scripts': ['pdf-diff=pdf_diff.command_line:main'],
      },
      zip_safe=False)
