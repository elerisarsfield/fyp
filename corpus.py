"""
Processing for information as language - corpora, documents and words
"""

import math
import random
import nltk
import numpy as np
import collections
import os
import pickle
from scipy import sparse


class Word():
    """Class for representing words and their senses"""

    def __init__(self, word, idx, senses):
        """
        Set up the word

        Parameters
        ----------
        word: the word being represented
        idx: the word's id in the vocabulary
        senses: the instances of the word in each sense
        """
        self.word = word
        self.idx = idx
        self.senses = np.zeros((senses, 2))

    def calculate(self):
        """
        Calculate the score according to novelty_diff method in Cook et al 2014

        Returns
        -------
        tuple of (max score, corresponding index)
        """
        indices = np.unique(np.nonzero(self.senses))
        stripped = self.senses[~np.all(self.senses == 0, axis=1)]
        scores = stripped/stripped.sum(axis=1)[:, None]
        novelty = scores[:, 1] - scores[:, 0]
        return (novelty.max(), indices[np.argmax(novelty)])


class Document():
    """Represents each document in a corpus"""

    def __init__(self, idx, doc, category):
        """
        Set up the document

        Parameters
        ----------
        idx: the documents's id in the corpus
        doc: a document in bag-of-words format
        category: whether the document is in reference or focus corpus
        """
        self.idx = idx
        self.partition = []
        self.topic_to_global_idx = []
        self.words = doc
        self.category = category

    def init_partition(self, alpha):
        """
        Setup the initial document partition according to CRP

        Parameters
        ----------
        alpha: value of alpha concentration parameter
        """
        N = 0
        for i in self.words:
            N += 1
            # Determine prior probabilities
            prior = [0] * len(self.partition)
            for j in range(len(self.partition)):
                probability = len(self.partition[j])/(N+alpha-1)
                prior[j] = probability
            new = alpha/(N+alpha-1)
            prior.append(new)
            # Pick a table
            table = random.random()
            if table > sum(prior[:-1]):
                self.partition.append([i])
            else:
                curr = 0
                for j, p in enumerate(prior):
                    curr += p
                    if curr > table:
                        self.partition[j].append(i)
                        break


class Corpus:
    """Represents a corpus"""

    def __init__(self, reference, output, focus=None, floor=1,
                 window_size=10):
        """
        Set up the corpus

        Parameters
        ----------
        reference: address of the reference corpus
        output: location to write saves to
        focus: address of the focus corpus
        floor: minimum number of word occurrences to require
        window_size: size of word window to consider
        """
        self.floor = floor + 1
        self.total_words = 0
        self.vocab_size = 0
        self.output = output
        self.word_counts = collections.Counter()
        self.docs = []
        self.word_to_idx = None
        self.it = 0
        self.sentences = self.get_documents(reference, 'reference')
        if focus:
            self.sentences += self.get_documents(focus, 'focus')
        self.vocab_size = len(self.word_counts)
        self.collocations(self.sentences, window_size)

    def get_documents(self, filepath, origin):
        """
        Split text into sentences and extract word counts

        Parameters
        ----------
        filepath: address of the document
        origin: whether reference or focus corpus

        Returns
        -------
        List of documents in bag-of-words format
        """
        with open(filepath, 'r') as f:
            sentences = self.preprocess([i.strip() for i in f])
            self.word_to_idx = {i: o for o,
                                i in enumerate(self.word_counts.keys())}

            self.idx_to_word = [i for i in self.word_to_idx.keys()]
            for i, s in enumerate(sentences):
                s = [self.word_to_idx[i] for i in s]
                doc = Document(i, s, origin)
                self.docs.append(doc)
            return sentences

    def preprocess(self, sentences):
        """
        Preprocess a list of documents

        Parameters
        ----------
        sentences: list of documents

        Returns
        -------
        List of documents in bag-of-words format
        """
        words = [j for i in sentences for j in nltk.word_tokenize(i)]
        word_counts = collections.Counter(words)
        stopwords = set(nltk.corpus.stopwords.words('english'))
        for i in word_counts.most_common()[::-1]:
            if i[1] < self.floor:
                stopwords.add(i[0])
        for i, s in enumerate(sentences):
            sentences[i] = [i for i in s.split(' ') if i not in stopwords]
        self.word_counts += collections.Counter(
            [j for i in sentences for j in i])
        return [i for i in sentences if len(i) > 0]

    def collocations(self, corpus, window_size=10):
        """
        Build the co-occurence matrix

        Parameters
        ----------
        corpus: list of documents in bag-of-words format
        window_size: size of word window to consider        
        """
        shape = (self.vocab_size, self.vocab_size)
        print('Starting co-occurence matrix build...')
        cooccurences = sparse.dok_matrix(shape)
        # Calculate raw occurrences
        for i in corpus:
            for j, k in enumerate(i):
                if k not in self.word_to_idx:
                    continue
                window_start = max(0, j - (window_size // 2))
                window_end = min(len(i) - 1, j + (window_size // 2))
                occurences = i[window_start:window_end]
                for l in occurences:
                    if l != k and l in self.word_to_idx:
                        a = self.word_to_idx[l]
                        b = self.word_to_idx[k]
                        cooccurences[a, b] += 1
        print('Computing PPMI...')
        ppmi = sparse.dok_matrix(shape)
        total = np.sum(cooccurences)
        # Compute PPMI
        for i, j in zip(
                np.nonzero(cooccurences)[0], np.nonzero(cooccurences)[1]):
            index_i = self.idx_to_word[i]
            index_j = self.idx_to_word[j]
            frequency = cooccurences[i, j]
            joint_probability = frequency / total
            probability_i = (frequency * self.word_counts[index_i]) / total
            probability_j = (frequency * self.word_counts[index_j]) / total
            denominator = probability_i * probability_j
            if denominator > 0:
                pmi = math.log(joint_probability /
                               (probability_i * probability_j), 2)
                ppmi[i, j] = max(0, pmi)
            else:
                ppmi[i, j] = 0
        print('finished computing')
        self.collocations = cooccurences
        self.shape = cooccurences.shape

    def save(self):
        """Save the corpus to a file"""
        self.it += 1
        filename = 'corpus_'+str(self.it)+'.pkl'
        out = os.path.join(self.output, filename)
        pickle.dump(self, open(out, 'wb'))
