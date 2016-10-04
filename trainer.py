import TextUtils
import codecs
import json
import re
import VectorUtils
from random import shuffle
import numpy as np
from sklearn.externals import joblib
from sklearn.feature_selection import f_classif, SelectKBest
from sklearn.ensemble import RandomForestClassifier


def train_word_embeddings(input_file, output_file=None, max_n_grams=1, dimensions=200, percent_non_zero=0.01,
                          additional_params=None):
    """
    A modular, lightweight word-embeddings trainer. The trainer is case-insensitive.
    At present, the implementation scans through the file twice, although it's possible to re-implement this algorithm
    so that we only need one pass. The latter is more useful for streaming data.
    :param input_file: an ordinary text file. We analyze the file at the level of tokens (using tokenizer functions
    in TextUtils). A new line represents a boundary i.e. the file is best thought of as a 'bag' (not 'list') of lines.
    :param output_file: If not None, write out the word embedding object in json lines format
    :param max_n_grams: learns embeddings for words up to this many token n-grams. At present only supported for
    unigrams (i.e. =1)
    :param dimensions: the number of dimensions in the embedding. We found 200 to work well in many of our experiments
    :param percent_non_zero: the number of non-zero elements in each context vector. Change at your own risk.
    :param additional_params: A dictionary of additional parameters. Currently only uses the context_window_size
    parameter, if one exists.
    :return: the word embedding object, which is a dict, with a word referencing its embedding.
    """
    if additional_params and 'context_window_size' in additional_params:
        context_window_size = additional_params['context_window_size']
    else:
        context_window_size = 2
    if max_n_grams != 1:
        raise Exception('At present, we only support unigram embeddings. Please set to 1, or use default.')
    set_of_words = set()
    with codecs.open(input_file, 'r', 'utf-8') as f:
        for line in f:
            set_of_words = set_of_words.union(set(TextUtils.tokenize_string(line.lower())))
    context_vector_dict = _generate_context_vectors(set_of_words, d=dimensions, non_zero_ratio=percent_non_zero)
    word_embeddings_obj = _init_word_embeddings_obj(context_vector_dict)
    with codecs.open(input_file, 'r', 'utf-8') as f:
        for line in f:
            list_of_tokens = TextUtils.tokenize_string(line.lower())
            v = list_of_tokens
            for i in range(0, len(v)):  # iterate over token list
                token = v[i]
                if token not in word_embeddings_obj:
                    continue
                min = i - context_window_size
                if min < 0:
                    min = 0
                max = i + context_window_size
                if max > len(v):
                    max = len(v)
                for j in range(min, max):   # iterate over context
                    if j == i:
                        continue
                    context_token = v[j]
                    if context_token not in context_vector_dict:
                        continue
                    word_embeddings_obj[token] = VectorUtils.add_vectors([word_embeddings_obj[token],
                                                                          context_vector_dict[context_token]])
    if output_file:
        out = codecs.open(output_file, 'w', 'utf-8')
        for k, v in word_embeddings_obj.items():
            answer = dict()
            answer[k] = v
            json.dump(answer, out)
            out.write('\n')
        out.close()
    return word_embeddings_obj


def train_doc_embeddings(input_file, word_embedding_object, output_file=None, word_embedding_file=None,
                         word_blacklist=None, additional_params=None):
    """
    A modular lightweight doc-embeddings trainer. The trainer is case-insensitive.
    Each doc-embedding is generated by adding all constituent word vectors. To prevent 'popular' words from
    overwhelming the doc-vec, we ignore all words that have a greater non-zero elements ratio than prune_threhsold.
    You can also (externally) preprocess the document so that stop-words etc. are removed, and set prune_threshold
    to 1.0 to disable its functionality.

    :param input_file: A tab-delimited file with the first field being the doc-id and the second field holding
    the tokens. The second field itself may contain tabs. doc_ids may occur in multiple lines; we will consider
    the union of all constituent words.
    :param word_embedding_object: the object that was returned by train_word_embeddings. More generally, this is
    simply a dict with words referencing vectors. You can use this code with other embeddings also.
    :param word_embedding_file: If you want to read the embeddings from a file.
    :param word_blacklist: typically stop-words. Can be superset of words in word embeddings. May be set of list.
    Will not consider these when composing doc-vecs.
    :param additional_params: Currently not in use. In the future, will be used to offer greater degrees
    of freedom
    :return: the doc embedding object, which is a dict, with doc-ids referencing the doc vector.
    """
    if not word_embedding_object:
        word_embedding_object = train_word_embeddings(word_embedding_file)
    if word_blacklist:
        blackset = set(word_blacklist)
    else:
        blackset = set()    # empty set, for compatibility with code below
    doc_embeddings_dict = dict()
    with codecs.open(input_file, 'r', 'utf-8') as f:
        for line in f:
            # print line
            fields = re.split('\t',line.lower())
            doc_id = fields[0]
            doc_vec = None
            list_of_tokens = TextUtils.tokenize_string(' '.join(fields[1:]))
            if doc_id in doc_embeddings_dict:
                doc_vec = doc_embeddings_dict[doc_id]
            for token in list_of_tokens:
                if token not in word_embedding_object:
                    continue
                elif token in blackset:
                    continue

                if not doc_vec:
                    doc_vec = list(word_embedding_object[token])
                else:
                    doc_vec = VectorUtils.add_vectors([doc_vec, word_embedding_object[token]])
            if doc_vec:
                doc_embeddings_dict[doc_id] = doc_vec
    if output_file:
        out = codecs.open(output_file, 'w', 'utf-8')
        for k, v in doc_embeddings_dict.items():
            answer = dict()
            answer[k] = v
            json.dump(answer, out)
            out.write('\n')
        out.close()
    return doc_embeddings_dict


def train_annotation_models(annotated_jlines_file, text_attribute, annotated_attribute, correct_attribute,
        word_embedding_object, classification_model_output_file, feature_model_output_file, word_embedding_file=None):
    """
    This is an involved function. For usage, see annotation_trainer_example in examples

    This version assumes the annotated file isn't too big, so it reads the whole thing into memory.
    We also have a memory-light version in a different package. You can also modify this function to make
    it more memory-efficient, but at the cost of 'merging' the various steps below, making the code
    harder to understand and debug.

    We use random forest and k-best feature selection for the actual models.
    :param annotated_jlines_file:
    :param text_attribute:
    :param annotated_attribute:
    :param correct_attribute:
    :param word_embedding_object: e.g. as output by train_word_embeddings
    :param word_embedding_file: in case you wrote out the embedding to file
    :return:
    """
    # first, get the embeddings object
    if not word_embedding_object:
        word_embedding_object = dict()
        if word_embedding_file:
            with codecs.open(word_embedding_file, 'r', 'utf-8') as f:
                for line in f:
                    obj = json.loads(line)
                    for k, v in obj.items():
                        word_embedding_object[k] = v
        else:
            raise Exception('you have not trained/specified a word embedding...')

    # second, read in the file and preprocess the data
    json_objects = list()
    with codecs.open(annotated_jlines_file, 'r', 'utf-8') as f:
        for line in f:
            obj = json.loads(line)
            tokenized_field = TextUtils.tokenize_field(obj, text_attribute)
            if tokenized_field:
                obj[text_attribute] = TextUtils.preprocess_tokens(tokenized_field, options=["lower"])
                for k in obj.keys():
                    obj[k] = TextUtils.preprocess_tokens(obj[k], options=["lower"])
            json_objects.append(obj)

    # third, generate and collect training vectors
    pos_features = list()
    neg_features = list()
    for obj in json_objects:
        for word in obj[annotated_attribute]:
            word_tokens = TextUtils.tokenize_string(word)
            if len(word_tokens) <= 1:  # we're dealing with a single word
                if word not in obj[text_attribute]:
                    print 'skipping word not found in text field: ',
                    print word
                    continue
                context_vecs = _context_generator(word, obj[text_attribute], word_embedding_object)
            elif TextUtils.is_sublist_in_big_list(obj[text_attribute], word_tokens):
                context_vecs = _context_generator(word, obj[text_attribute], word_embedding_object, multi=True)
            else:
                continue

            if not context_vecs:
                print 'context_generator did not return anything for word: ',
                print word
                continue

            for context_vec in context_vecs:
                if word in obj[correct_attribute]:
                    pos_features.append(context_vec)
                else:
                    neg_features.append(context_vec)
    if not pos_features or not neg_features:
        raise Exception('One (or both) of the positive/negative feature sets is empty. Exiting...')
    features = dict()
    features[0] = VectorUtils.normalize_matrix(np.matrix(neg_features))
    features[1] = VectorUtils.normalize_matrix(np.matrix(pos_features))
    data_dict = _prepare_training_data(features)

    # four, train the model and write out the various models to the output
    kBest = SelectKBest(f_classif, k=20)
    kBest = kBest.fit(data_dict['train_data'], data_dict['train_labels'])
    joblib.dump(kBest, feature_model_output_file)
    data_dict['train_data'] = kBest.transform(data_dict['train_data'])
    model = RandomForestClassifier()
    model.fit(data_dict['train_data'], data_dict['train_labels'])
    joblib.dump(model, classification_model_output_file)


def _prepare_training_data(data_vectors, balanced_training=True):
    """
    For internal use only. data_vectors is a simple 2-element dictionary with 0 referencing a matrix of
    negative vectors, and 1 a matrix of positive vectors
    :param balanced_training: if True, we will equalize positive and negative training samples by oversampling
    the lesser class. For example, if we have 4 positive samples and 7 negative samples, we will randomly re-sample
    3 positive samples from the 4 positive samples, meaning there will be repetition. Use with caution.
    :param data_vectors: a dictionary containing the positive negative samples
    :return: dictionary containing training/testing data/labels
    """
    data = data_vectors
    train_pos_num = len(data[1])
    train_neg_num = len(data[0])
    train_data_pos = data[1]
    train_data_neg = data[0]
    if balanced_training:
        if train_pos_num < train_neg_num:
            train_labels_pos = [[1] * train_neg_num]
            train_labels_neg = [[0] * train_neg_num]
            train_data_pos = _sample_and_extend(train_data_pos, total_samples=train_neg_num)
        elif train_pos_num > train_neg_num:
            train_labels_pos = [[1] * train_pos_num]
            train_labels_neg = [[0] * train_pos_num]
            train_data_neg = _sample_and_extend(train_data_neg, total_samples=train_pos_num)
        else:
            train_labels_pos = [[1] * train_pos_num]
            train_labels_neg = [[0] * train_neg_num]
    else:
        train_labels_pos = [[1] * train_pos_num]
        train_labels_neg = [[0] * train_neg_num]

    train_data = np.append(train_data_pos, train_data_neg, axis=0)
    train_labels = np.append(train_labels_pos, train_labels_neg)
    results = dict()
    results['train_data'] = train_data
    results['train_labels'] = train_labels
    return results


def _sample_and_extend(list_of_vectors, total_samples):
    """
    Oversampling code for balanced training. We will do deep re-sampling, assuming that the vectors contain
    atoms.
    :param list_of_vectors: the list of vectors that are going to be re-sampled (randomly)
    :param total_samples: The total number of vectors that we want in the list. Make sure that this number
    is higher than the length of list_of_vectors
    :return: the over-sampled list
    """
    if len(list_of_vectors) >= total_samples:
        raise Exception('Check your lengths!')

    indices = range(0, len(list_of_vectors))
    shuffle(indices)
    desired_samples = total_samples - len(list_of_vectors)
    # print desired_samples>len(list_of_vectors)
    while desired_samples > len(indices):
        new_indices = list(indices)
        shuffle(new_indices)
        indices += new_indices
    new_data = [list(list_of_vectors[i]) for i in indices[0:desired_samples]]
    # print new_data
    return np.append(list_of_vectors, new_data, axis=0)


def _context_generator(word, list_of_words, embeddings_dict, window_size=2, multi=False):
    """
        The algorithm will search for occurrences of word in list_of_words (there could be multiple or even 0), then
        symmetrically look backward and forward up to the window_size. If the words in the window (not including
        the word itself) are in the embeddings_dict, we will add them up, and that constitutes a context_vec.
        If the word is not there in embeddings_dict, we do not include it. Note that if no words in the embeddings_dict
        then we will act as if the word itself had never occurred in the list_of_words.
        :param word:
        :param list_of_words: a list of words
        :param embeddings_dict: the word embedding object
        :param window_size
        :param multi: If True, then word is multi-token. You must tokenize it first, then generate context embedd.
        :return: a list of lists, with each inner list representing the context vectors. If there are no occurrences
        of word, will return None. Check for this in your code.
    """
    if not list_of_words:
        return None
    context_vecs = list()
    if multi:
        word_tokens = TextUtils.tokenize_string(word)
    for i in range(0, len(list_of_words)):
        if multi:
            if list_of_words[i] == word_tokens[0] and list_of_words[i:i + len(word_tokens)] == word_tokens:
                min_index = i - window_size
                max_index = ((i + len(word_tokens)) - 1) + window_size
            else:
                continue
        elif list_of_words[i] != word:
            continue
        else:
            min_index = i - window_size
            max_index = i + window_size

        # make sure the indices are within range
        if min_index < 0:
            min_index = 0
        if max_index >= len(list_of_words):
            max_index = len(list_of_words) - 1

        new_context_vec = []
        for j in range(min_index, max_index + 1):
            if multi:  # we do not want the vector of the word/work_tokens itself
                if i+len(word_tokens) < j >= i:
                    continue
            elif j == i:
                continue

            if list_of_words[j] not in embeddings_dict:  # is the word even in our embeddings?
                continue

            vec = list(embeddings_dict[list_of_words[j]])  # deep copy of list
            if not new_context_vec:
                new_context_vec = vec
            else:
                new_context_vec = VectorUtils.add_vectors([new_context_vec, vec])
        if not new_context_vec:
            continue
        else:
            context_vecs.append(new_context_vec)
    if not context_vecs:
        return None
    else:
        return context_vecs


def _generate_random_sparse_vector(d, non_zero_ratio):
    """
    Suppose d =200 and the ratio is 0.01. Then there will be 2 +1s and 2 -1s and all the rest are 0s.
    :param d: the number of dimensions
    :param non_zero_ratio:
    :return: a randomly generated vector with d dimensions
    """
    answer = [0]*d
    indices = [i for i in range(d)]
    shuffle(indices)
    k = int(non_zero_ratio*d)
    for i in range(0, k):
        answer[indices[i]] = 1
    for i in range(k, 2*k):
        answer[indices[i]] = -1
    return answer


def _generate_context_vectors(set_of_words, d, non_zero_ratio):
    """
    Generate context vectors. For info on the dummies, see notes.txt
    :param idf_dict:
    :param include_dummies: If true, then we will append several 'dummy' keys in idf_dict, and generate context
    vectors for those as well.
    :param d:
    :param non_zero_ratio:
    :return: A dictionary with the word as key, and a context vector as value.
    """
    context_dict = dict()
    for k in set_of_words:
        context_dict[k] = _generate_random_sparse_vector(d, non_zero_ratio)
    return context_dict


def _init_word_embeddings_obj(context_vec_dict):
    embeddings = dict()
    for k, v in context_vec_dict.items():
        embeddings[k] = list(v)  # deep copy of list
    return embeddings