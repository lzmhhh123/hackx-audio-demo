import face_recognition

lmm_image = face_recognition.load_image_file("faces/obama.jpg")
lmm_face_encoding = face_recognition.face_encodings(lmm_image)[0]

#al_image = face_recognition.load_image_file("faces/nuo.jpg")
#al_face_encoding = face_recognition.face_encodings(al_image)[0]

known_faces = [lmm_face_encoding]

import torch
from torch.autograd import Variable as V
import torchvision.models as models
from torchvision import transforms as trn
from torch.nn import functional as F
import os
import numpy as np
from scipy.misc import imresize as imresize
import cv2
from PIL import Image
import util
import json
import sys

def load_labels():
    # prepare all the labels
    # scene category relevant
    file_name_category = 'categories_places365.txt'
    if not os.access(file_name_category, os.W_OK):
        synset_url = 'https://raw.githubusercontent.com/csailvision/places365/master/categories_places365.txt'
        os.system('wget ' + synset_url)
    classes = list()
    with open(file_name_category) as class_file:
        for line in class_file:
            classes.append(line.strip().split(' ')[0][3:])
    classes = tuple(classes)

    # indoor and outdoor relevant
    file_name_IO = 'IO_places365.txt'
    if not os.access(file_name_IO, os.W_OK):
        synset_url = 'https://raw.githubusercontent.com/csailvision/places365/master/IO_places365.txt'
        os.system('wget ' + synset_url)
    with open(file_name_IO) as f:
        lines = f.readlines()
        labels_IO = []
        for line in lines:
            items = line.rstrip().split()
            labels_IO.append(int(items[-1]) -1) # 0 is indoor, 1 is outdoor
    labels_IO = np.array(labels_IO)

    # scene attribute relevant
    file_name_attribute = 'labels_sunattribute.txt'
    if not os.access(file_name_attribute, os.W_OK):
        synset_url = 'https://raw.githubusercontent.com/csailvision/places365/master/labels_sunattribute.txt'
        os.system('wget ' + synset_url)
    with open(file_name_attribute) as f:
        lines = f.readlines()
        labels_attribute = [item.rstrip() for item in lines]
    file_name_W = 'W_sceneattribute_wideresnet18.npy'
    if not os.access(file_name_W, os.W_OK):
        synset_url = 'http://places2.csail.mit.edu/models_places365/W_sceneattribute_wideresnet18.npy'
        os.system('wget ' + synset_url)
    W_attribute = np.load(file_name_W)

    return classes, labels_IO, labels_attribute, W_attribute

def hook_feature(module, input, output):
    features_blobs.append(np.squeeze(output.data.cpu().numpy()))

def returnCAM(feature_conv, weight_softmax, class_idx):
    # generate the class activation maps upsample to 256x256
    size_upsample = (256, 256)
    nc, h, w = feature_conv.shape
    output_cam = []
    for idx in class_idx:
        cam = weight_softmax[class_idx].dot(feature_conv.reshape((nc, h*w)))
        cam = cam.reshape(h, w)
        cam = cam - np.min(cam)
        cam_img = cam / np.max(cam)
        cam_img = np.uint8(255 * cam_img)
        output_cam.append(imresize(cam_img, size_upsample))
    return output_cam

def returnTF():
# load the image transformer
    tf = trn.Compose([
        trn.Scale((224,224)),
        trn.ToTensor(),
        trn.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])
    return tf


def load_model():
    # this model has a last conv feature map as 14x14

    model_file = 'whole_wideresnet18_places365.pth.tar'
    if not os.access(model_file, os.W_OK):
        os.system('wget http://places2.csail.mit.edu/models_places365/' + model_file)
        os.system('wget https://raw.githubusercontent.com/csailvision/places365/master/wideresnet.py')
    useGPU = 0
    if useGPU == 1:
        model = torch.load(model_file)
    else:
        model = torch.load(model_file, map_location=lambda storage, loc: storage) # allow cpu

    ## if you encounter the UnicodeDecodeError when use python3 to load the model, add the following line will fix it. Thanks to @soravux
    # from functools import partial
    # import pickle
    # pickle.load = partial(pickle.load, encoding="latin1")
    # pickle.Unpickler = partial(pickle.Unpickler, encoding="latin1")
    # model = torch.load(model_file, map_location=lambda storage, loc: storage, pickle_module=pickle)

    model.eval()
    # hook the feature extractor
    features_names = ['layer4','avgpool'] # this is the last conv layer of the resnet
    for name in features_names:
        model._modules.get(name).register_forward_hook(hook_feature)
    return model


# load the labels
classes, labels_IO, labels_attribute, W_attribute = load_labels()

# load the model
features_blobs = []
model = load_model()

# load the transformer
tf = returnTF() # image transformer

# get the softmax weight
params = list(model.parameters())
weight_softmax = params[-2].data.numpy()
weight_softmax[weight_softmax<0] = 0

# load the test image
#img_url = 'http://places2.csail.mit.edu/imgs/12.jpg'
#os.system('wget %s -q -O test.jpg' % img_url)
#img = Image.open('test.jpg')
#input_img = V(tf(img).unsqueeze(0), volatile=True)

def generate_result(filename):
    #filename = 'funny.mp4'
    frames = util.get_frames("./build/videos/"+filename)
    scenes = util.get_scenes(frames)
    scenes = np.array(scenes)

    img_shape = frames[0].shape
    result_dict = {'filename':filename, 'height':img_shape[1], 
                    'width':img_shape[2], 'scenes':{}}
    
    for i in range(len(scenes)):
        if scenes[i] + 5 < len(frames):
            scenes[i] = scenes[i] + 5


    for i,img in enumerate(frames[scenes]):

        face_locations = face_recognition.face_locations(img)
        face_encodings = face_recognition.face_encodings(img, face_locations)

        #face_names = []
        for face_encoding in face_encodings:
            # See if the face is a match for the known face(s)
            match = face_recognition.compare_faces(known_faces, face_encoding, tolerance=0.50)

            # If you had more than 2 faces, you could make this logic a lot prettier
            # but I kept it simple for the demo
            name = None
            if match[0]:
                name = "obama"
            #elif match[1]:
            #    name = "nuo"i
            	print scenes[i], name

        # forward pass
        #img = cv2.imencode('.jpg', img)
        img = Image.fromarray(img)
        img.save("./build/videos/" + filename[:-4] + ".jpg")
        img = V(tf(img).unsqueeze(0), volatile=True)
        
        logit = model.forward(img)
        h_x = F.softmax(logit).data.squeeze()
        probs, idx = h_x.sort(0, True)
        print('RESULT ON ', scenes[i]/24.0)
        io_image = np.mean(labels_IO[idx[:10].numpy()]) # vote for the indoor or outdoor
        if io_image < 0.5:
            print('--TYPE OF ENVIRONMENT: indoor')
        else:
            print('--TYPE OF ENVIRONMENT: outdoor')
        # output the prediction of scene category
        print('--SCENE CATEGORIES:')
        print('{:.3f} -> {}'.format(probs[0], classes[idx[0]]))
        if probs[0] <= 0.10:
            result_dict['scenes'][i] = {'time':scenes[i]/24.0,
                                    'scenes_categories':"Unkown"}
        if probs[0] <= 0.20 and probs[0] > 0.10:
            if io_image < 0.5:
                result_dict['scenes'][i] = {'time':scenes[i]/24.0,
                                    'scenes_categories':"indoor"}
            else:
                result_dict['scenes'][i] = {'time':scenes[i]/24.0,
                                        'scenes_categories':"outdoor"}
        else:
            result_dict['scenes'][i] = {'time':scenes[i]/24.0,
                                    'scenes_categories':classes[idx[0]]}
        
        #print(result_dict)

        with open('./build/videos/'+str(filename[:-4])+'.json', 'w') as outfile:
            json.dump(result_dict, outfile)

        # output the scene attributes
        #responses_attribute = W_attribute.dot(features_blobs[1])
        #idx_a = np.argsort(responses_attribute)
        #print('--SCENE ATTRIBUTES:')
        #print(', '.join([labels_attribute[idx_a[i]] for i in range(-1,-10,-1)]))


if __name__ == "__main__":
    generate_result(sys.argv[1])
