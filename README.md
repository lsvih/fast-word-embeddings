This python module is designed for learning fast lightweight 'word embeddings' based on random indexing algorithms in the dimensionality reduction literature. We have experimentally verified the word embeddings to work well in noisy Web domains (like human trafficking). The functions in the module are simple, come with example-usage code snippets and are highly scalable, with minimum memory requirements. They are designed to take raw text files as input, so you do minimal (if any) preprocessing down your end. They make use of simple python libraries. They also contain experimental code for embedding 'documents' into vector spaces, and for learning machine learning models that help you do better information extraction over Web pages.

The packages that you need to install to get this module  working on python 2.7 are all on pip and commonly used. You should start with nltk 'book' by running nltk.download() in your environment (or the command line) and installing the book package (you can install other packages as well but know that it takes a lot more time!); other packages are numpy and scikit-learn. Make sure that your version of scikit-learn supports joblib, if you intend to dump learned machine learning models out to file.  

The code in this module fully supports utf-8 encodings, so you do not have to worry about stripping out unicodes from your files.

We have provided usage examples for all utilities in this repo in examples.py. You can use any of those functions with minimal changes to get the code working for you (assuming the project environment is correctly set up). Example datasets that are used in examples.py are provided in fast-word-embeddings-datasets for you to start playing with the code quickly. This code is being actively maintained at present; please open up issues if you notice any. The initial version of this module has been designed for the End Human Trafficking Hackathon being held in New York City from OCt 7 to 9, 2016.
