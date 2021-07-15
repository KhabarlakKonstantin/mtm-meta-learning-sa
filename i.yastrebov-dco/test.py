# -*- coding: utf-8 -*-
import argparse
import numpy as np
import os
import torch
import torch.nn.functional as F

from models.classification_heads import ClassificationHead
from models.protonet_embedding import ProtoNetEmbedding
from models.ResNet12_embedding import resnet12
from torchmeta.transforms import Categorical, ClassSplitter
from torchmeta.utils.data import BatchMetaDataLoader
from torchvision.transforms import ColorJitter, Compose, Normalize, RandomCrop, RandomHorizontalFlip, ToTensor
from tqdm import tqdm
from utils import check_dir, count_accuracy, log, set_gpu, Timer 

def get_model(options):
    # Choose the embedding network
    if options.network == 'ProtoNet':
        network = ProtoNetEmbedding().cuda()
    elif options.network == 'ResNet':
        if options.dataset == 'miniImageNet' or options.dataset == 'tieredImageNet':
            network = resnet12(avg_pool = False, drop_rate = .1, dropblock_size = 5).cuda()
            if opt.gpu != '0':
                network = torch.nn.DataParallel(network, device_ids=[0, 1, 2, 3])
        else:
            network = resnet12(avg_pool = False, drop_rate = .1, dropblock_size = 2).cuda()
    else:
        print ("Cannot recognize the network type")
        assert(False)
        
    # Choose the classification head
    if options.head == 'Ridge':
        cls_head = ClassificationHead(base_learner='Ridge').cuda()
    elif options.head == 'Proto':
        cls_head = ClassificationHead(base_learner='Proto').cuda()
    elif options.head == 'SVM-CS':
        cls_head = ClassificationHead(base_learner='SVM-CS').cuda()
    elif options.head == 'SVM-He':
        cls_head = ClassificationHead(base_learner='SVM-He').cuda()
    elif options.head == 'SVM-WW':
        cls_head = ClassificationHead(base_learner='SVM-WW').cuda()
    else:
        print ("Cannot recognize the base learner type")
        assert(False)
        
    return (network, cls_head)

def get_dataset(options):
    # Choose the embedding network
    if options.dataset == 'miniImageNet':
        from torchmeta.datasets import MiniImagenet
        mean_pix = [x / 255 for x in [129.37731888, 124.10583864, 112.47758569]]
        std_pix = [x / 255 for x in [68.20947949, 65.43124043, 70.45866994]]
        dataset_test = MiniImagenet(
          "data",
            num_classes_per_task = opt.way,
            transform = Compose([ToTensor(),
                                 Normalize(mean = mean_pix,
                                           std = std_pix),
                                ]),
            target_transform = Categorical(num_classes = opt.way),
            meta_test = True,
            download = True)
        dataset_test = ClassSplitter(dataset_test, shuffle = True,
                                     num_train_per_class = opt.shot,
                                     num_test_per_class = opt.query)
        dataloader_test = BatchMetaDataLoader(
            dataset_test,
            batch_size = 1,
            num_workers = opt.num_workers)
    elif options.dataset == 'tieredImageNet':
        from torchmeta.datasets import TieredImagenet
        mean_pix = [x / 255 for x in [129.37731888, 124.10583864, 112.47758569]]
        std_pix = [x / 255 for x in [68.20947949, 65.43124043, 70.45866994]]
        dataset_test = TieredImagenet(
          "data",
            num_classes_per_task = opt.way,
            transform = Compose([ToTensor(),
                                 Normalize(mean = mean_pix,
                                           std = std_pix),
                                ]),
            target_transform = Categorical(num_classes = opt.way),
            meta_test = True,
            download = True)
        dataset_test = ClassSplitter(dataset_test, shuffle = True,
                                     num_train_per_class = opt.shot,
                                     num_test_per_class = opt.query)
        dataloader_test = BatchMetaDataLoader(
            dataset_test,
            batch_size = 1,
            num_workers = opt.num_workers)
    elif options.dataset == 'CIFAR_FS':
        from torchmeta.datasets import CIFARFS
        mean_pix = [x/255.0 for x in [129.37731888, 124.10583864, 112.47758569]]
        std_pix = [x/255.0 for x in [68.20947949, 65.43124043, 70.45866994]]
        dataset_test = CIFARFS(
          "data",
            num_classes_per_task = opt.way,
            transform = Compose([ToTensor(),
                                 Normalize(mean = mean_pix,
                                           std = std_pix),
                                ]),
            target_transform = Categorical(num_classes = opt.way),
            meta_test = True,
            download = True)
        dataset_test = ClassSplitter(dataset_test, shuffle = True,
                                     num_train_per_class = opt.shot,
                                     num_test_per_class = opt.query)
        dataloader_test = BatchMetaDataLoader(
            dataset_test,
            batch_size = 1,
            num_workers = opt.num_workers)
    elif options.dataset == 'FC100':
        from torchmeta.datasets import FC100
        mean_pix = [x/255.0 for x in [129.37731888, 124.10583864, 112.47758569]]
        std_pix = [x/255.0 for x in [68.20947949, 65.43124043, 70.45866994]]
        dataset_test = FC100(
            "data",
            num_classes_per_task = opt.way,
            transform = Compose([ToTensor(),
                                 Normalize(mean = mean_pix,
                                           std = std_pix),
                                ]),
            target_transform = Categorical(num_classes = opt.way),
            meta_test = True,
            download = True)
        dataset_test = ClassSplitter(dataset_test, shuffle = True,
                                     num_train_per_class = opt.shot,
                                     num_test_per_class = opt.query)
        dataloader_test = BatchMetaDataLoader(
            dataset_test,
            batch_size = 1,
            num_workers = opt.num_workers)
    else:
        print ("Cannot recognize the dataset type")
        assert(False)
        
    return dataloader_test

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--gpu', default='0')
    parser.add_argument('--num-workers', type=int, default=2,
                            help='number of cpu workers for loading data')
    parser.add_argument('--load', default='./experiments/best_model.pth',
                            help='path of the checkpoint file')
    parser.add_argument('--episode', type=int, default=1000,
                            help='number of episodes to test')
    parser.add_argument('--way', type=int, default=5,
                            help='number of classes in one test episode')
    parser.add_argument('--shot', type=int, default=1,
                            help='number of support examples per training class')
    parser.add_argument('--query', type=int, default=15,
                            help='number of query examples per training class')
    parser.add_argument('--network', type=str, default='ResNet',
                            help='choose which embedding network to use. ResNet')
    parser.add_argument('--head', type=str, default='SVM-CS',
                            help='choose which classification head to use. Ridge, SVM')
    parser.add_argument('--dataset', type=str, default='miniImageNet',
                            help='choose which classification head to use. miniImageNet, tieredImageNet, CIFAR_FS, FC100')

    opt = parser.parse_args()
    
    dataloader_test = get_dataset(opt)

    set_gpu(opt.gpu)
    
    log_file_path = os.path.join(os.path.dirname(opt.load), "test_log.txt")
    log(log_file_path, str(vars(opt)))

    # Define the models
    (embedding_net, cls_head) = get_model(opt)
    
    # Load saved model checkpoints
    saved_models = torch.load(opt.load)
    embedding_net.load_state_dict(saved_models['embedding'])
    embedding_net.eval()
    cls_head.load_state_dict(saved_models['head'])
    cls_head.eval()
    
    # Evaluate on test set
    test_accuracies = []
    with tqdm(dataloader_test, total = opt.episode, initial = 1) as pbar:
      for i, batch in enumerate(pbar, 1):
        data_support, labels_support = batch["train"]
        data_query, labels_query = batch["test"]
        data_support = data_support.to(device='cuda')
        labels_support = labels_support.to(device='cuda')
        data_query = data_query.to(device='cuda')
        labels_query = labels_query.to(device='cuda')

        n_support = opt.way * opt.shot
        n_query = opt.way * opt.query
                
        emb_support = embedding_net(data_support.reshape([-1] + list(data_support.shape[-3:])))
        emb_support = emb_support.reshape(1, n_support, -1)
        
        emb_query = embedding_net(data_query.reshape([-1] + list(data_query.shape[-3:])))
        emb_query = emb_query.reshape(1, n_query, -1)

        if opt.head in ['SVM-CS', 'SVM-He', 'SVM-WW']:
            logits = cls_head(emb_query, emb_support, labels_support, opt.way, opt.shot, maxIter=3)
        else:
            logits = cls_head(emb_query, emb_support, labels_support, opt.way, opt.shot)

        acc = count_accuracy(logits.reshape(-1, opt.way), labels_query.reshape(-1))
        test_accuracies.append(acc.item())
        
        avg = np.mean(np.array(test_accuracies))
        std = np.std(np.array(test_accuracies))
        ci95 = 1.96 * std / np.sqrt(i + 1)
        
        if i % (opt.episode / 20) == 0:
            print('Episode [{}/{}]:\t\t\tAccuracy: {:.2f} ± {:.2f} % ({:.2f} %)'\
                  .format(i, opt.episode, avg, ci95, acc))
        if i == opt.episode:
            break
