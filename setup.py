from setuptools import setup, find_packages

setup(name='pdf-diff',
      version='0.9.1',
      description='Finds differences between two PDF documents',
      long_description=open("README.md").read(),
      long_description_content_type="text/markdown",
      url='https://github.com/JoshData/pdf-diff',
      author=u'Joshua Tauberer',
      author_email=u'jt@occams.info',
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
