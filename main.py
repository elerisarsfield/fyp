import nltk
import scipy.spatial.distance as dist
import argparse
import time
import os
import utils
from corpus import Corpus, Word
from hdp import HDP

parser = argparse.ArgumentParser()
parser.add_argument(
    'start_corpus', type=str, help='address of the older (reference) corpus')
parser.add_argument('end_corpus', type=str,
                    help='address of the newer (focus) corpus')
parser.add_argument('--semeval_mode', type=bool, help='True if the project is being used for SemEval 2020 Task 1, False if the project is being used for general inference, default False', default=False, metavar='M')
parser.add_argument('targets', type=str, help='address of the target words', nargs='?')
parser.add_argument('output', type=str, help='address to write output to')
parser.add_argument('--max_iters', type=int, metavar='N', default=25,
                    help='maximum number of iterations to run sampling for')
parser.add_argument('--alpha', type=float, default=1.0,
                    help='alpha value, default 1.0')
parser.add_argument('--gamma', type=float, default=1.0,
                    help='gamma value, default 1.0')
parser.add_argument('--eta', type=float, default=0.1,
                    help='eta value, default 0.1')
parser.add_argument('--window_size', metavar='W', type=int, default=10,
                    help='size of context window to use, default 10')
parser.add_argument('--floor', type=int, metavar='F', default=1,
                    help='minimum number of occurrences to be considered, default 1')

args = parser.parse_args()
if args.semeval_mode and 'targets' not in vars(args):
    parser.error('targets arg is required when in SemEval mode')

def main():
    start_time = time.time()
    try:
        nltk.data.find('corpora/stopwords')
    except LookupError:
        nltk.download('stopwords')
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        nltk.download('punkt')

    if not os.path.exists(args.output):
        os.makedirs(args.output)

    save_path = os.path.join(args.output, 'saves')
    if not os.path.exists(save_path):
        os.makedirs(save_path)

    print('Loading words...')
    corpus = Corpus(args.start_corpus, save_path, args.end_corpus, args.floor, args.window_size)
    print('Setting up initial partition...')
    for i in corpus.docs:
        i.init_partition(args.alpha)

    hdp = HDP(corpus.vocab_size, save_path, eta=args.eta, alpha=args.alpha, gamma=args.gamma)
    hdp.init_partition(corpus.docs)
    for i in corpus.docs:
        i.topic_to_distribution(hdp.senses.shape[0])

    print('Done')
    it = 0
    stopping = 1.0
    print(f'Running Gibbs sampling for {args.max_iters} iterations...')
    while it < args.max_iters:
        it += 1
        for j in corpus.docs:
            for i in range(len(j.words)):
                hdp.sample_table(j, i, corpus.collocations[j.words[i]])
        if it % 5 == 0:
            corpus.save()
            print(f'Finished {it} iterations')
    for i in hdp.senses:
        i /= i.sum()
    print('Done')
    print('Generating scores for word senses...')
    words = dict()
    for j in corpus.docs:
        for i, p in enumerate(j.partition):
            origin = j.category
            sense = j.topic_to_global_idx[i]
            for w in p:
                if corpus.idx_to_word[w] in words:
                    if origin == 'reference':
                        words[corpus.idx_to_word[w]].senses[sense][0] += 1
                    else:
                        words[corpus.idx_to_word[w]].senses[sense][1] += 1
                else:
                    word = Word(corpus.idx_to_word[w], w, hdp.senses.shape[0])
                    if origin == 'reference':
                        word.senses[sense][0] += 1
                    else:
                        word.senses[sense][1] += 1
                    words[word.word] = word

    for k, v in words.items():
        v = v.calculate()
    assert max(words.values()) <= 1
    assert min(words.values()) >= 0
    if args.semeval_mode:
        print(f'Running separate inference on the two corpora...')
        targets = utils.get_targets(args.targets)
        corpus1 = Corpus(args.start_corpus, save_path, floor=args.floor, window_size=args.window_size)
        corpus2 = Corpus(args.start_corpus, save_path, floor=args.floor, window_size=args.window_size)
        hdp = HDP(corpus1.vocab_size, save_path, eta=args.eta, alpha=args.alpha, gamma=args.gamma)
        hdp.init_partition(corpus1.docs)
        it = 0
        while it < args.max_iters:
            it += 1
            for j in corpus.docs:
                for i in range(len(j.words)):
                    hdp.sample_table(j, i, corpus1.collocations[j.words[i]])
        for i in hdp.senses:
            i /= i.sum()
        dist_1 = hdp.senses
        hdp = HDP(corpus2.vocab_size, save_path, eta=args.eta, alpha=args.alpha, gamma=args.gamma)
        hdp.init_partition(corpus2.docs)
        it = 0
        while it < args.max_iters:
            it += 1
            for j in corpus.docs:
                for i in range(len(j.words)):
                    hdp.sample_table(j, i, corpus2.collocations[j.words[i]])
        for i in hdp.senses:
            i /= i.sum()
        dist_2 = hdp.senses
        for i in targets:
            index = (corpus1.word_to_idx[i], corpus2.word_to_idx[i])
            jensenshannon = dist.jensenshannon(dist1[index[0]], dist2[index[1]])
        print('Done.')
        
    for i in corpus.docs:
        i.topic_to_distribution(hdp.senses.shape[0])

    else:
        top_k = 50
        top = sorted(words, key=words.get, reverse=True)[:top_k]
        print(f'Top {top_k} most differing words:')
        print(top)
    end_time = time.time()
    print(f'Ran project in {end_time - start_time} seconds')


if __name__ == '__main__':
    main()
