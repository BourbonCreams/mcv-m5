# Imports
from keras import backend as K
dim_ordering = K.image_dim_ordering()
from keras.callbacks import Callback, Progbar, ProgbarLogger
from keras.engine.training import GeneratorEnqueuer
from tools.save_images import save_img3
from tools.plot_history import plot_history
import numpy as np
import time

# PROGBAR replacements
def progbar__set_params(self, params):
    self.params = params
    print('Anado metrics!!!!!!!!: ' + str(self.add_metrics))
    self.params['metrics'].extend(self.add_metrics)


def progbar_on_epoch_begin(self, epoch, logs={}):
    if self.verbose:
        print('Epoch %d/%d' % (epoch + 1, self.nb_epoch))
        self.progbar = Progbar(target=self.params['nb_sample'],
                               verbose=self.verbose)
    # self.params['metrics'].extend(self.add_metrics)
    self.seen = 0


def progbar_on_batch_end(self, batch, logs={}):
    batch_size = logs.get('size', 0)
    self.seen += batch_size

    for k in self.params['metrics']:
        if k in logs and k not in self.remove_metrics:
            self.log_values.append((k, logs[k]))

    for k in self.add_metrics:
        if k in logs and k not in self.remove_metrics:
            self.log_values.append((k, logs[k]))

    # skip progbar update for the last batch;
    # will be handled by on_epoch_end
    if self.verbose and self.seen < self.params['nb_sample']:
        self.progbar.update(self.seen, self.log_values)


def progbar_on_epoch_end(self, epoch, logs={}):
    for k in self.params['metrics']:
        if k in logs and k not in self.remove_metrics:
            self.log_values.append((k, logs[k]))

    for k in self.add_metrics:
        if k in logs and k not in self.remove_metrics:
            self.log_values.append((k, logs[k]))

    if self.verbose:
        self.progbar.update(self.seen, self.log_values, force=True)


# Plot history
class History_plot(Callback):

    # Constructor
    def __init__(self, n_classes, savepath, train_metrics, valid_metrics,
                 best_metric, best_type, verbose=False, *args):
        super(Callback, self).__init__()
        # Save input parameters
        self.n_classes = n_classes
        self.savepath = savepath
        self.verbose = verbose
        self.train_metrics = train_metrics
        self.valid_metrics = valid_metrics
        self.best_metric = best_metric
        self.best_type = best_type

    def on_train_begin(self, logs={}):
        self.epoch = []
        self.history = {}

    def on_epoch_end(self, epoch, logs={}):
        self.epoch.append(epoch)
        for k, v in logs.items():
            self.history.setdefault(k, []).append(v)

        plot_history(self.history, self.savepath, self.n_classes,
                     train_metrics=self.train_metrics,
                     valid_metrics=self.valid_metrics,
                     best_metric=self.best_metric,
                     best_type=self.best_type,
                     verbose=self.verbose)


# Compute the jaccard value
class Jacc_new(Callback):

    # Constructor
    def __init__(self, n_classes, *args):
        super(Callback, self).__init__()
        # Save input parameters
        self.n_classes = n_classes
        self.I = np.zeros(self.n_classes)
        self.U = np.zeros(self.n_classes)
        self.jacc_percl = np.zeros(self.n_classes)
        self.val_I = np.zeros(self.n_classes)
        self.val_U = np.zeros(self.n_classes)
        self.val_jacc_percl = np.zeros(self.n_classes)

        self.remove_metrics = []
        for i in range(n_classes):
            self.remove_metrics.append('I' + str(i))
            self.remove_metrics.append('U' + str(i))
            self.remove_metrics.append('val_I' + str(i))
            self.remove_metrics.append('val_U' + str(i))

        self.add_metrics = []
        self.add_metrics.append('jaccard')
        self.add_metrics.append('val_jaccard')
        for i in range(n_classes):
            self.add_metrics.append(str(i) + '_jacc')
            self.add_metrics.append(str(i) + '_val_jacc')
        setattr(ProgbarLogger, 'add_metrics', self.add_metrics)
        setattr(ProgbarLogger, 'remove_metrics', self.remove_metrics)
        setattr(ProgbarLogger, '_set_params', progbar__set_params)
        setattr(ProgbarLogger, 'on_batch_end', progbar_on_batch_end)
        setattr(ProgbarLogger, 'on_epoch_end', progbar_on_epoch_end)

    def on_batch_end(self, batch, logs={}):
        for i in range(self.n_classes):
            self.I[i] = logs['I'+str(i)]
            self.U[i] = logs['U'+str(i)]
            self.jacc_percl[i] = self.I[i] / self.U[i]
            # logs[str(i)+'_jacc'] = self.jacc_percl[i]
        self.jacc_percl = self.I / self.U
        self.jacc = np.nanmean(self.jacc_percl)
        logs['jaccard'] = self.jacc


    def on_epoch_end(self, epoch, logs={}):
        for i in range(self.n_classes):
            self.I[i] = logs['I'+str(i)]
            self.U[i] = logs['U'+str(i)]
            self.jacc_percl[i] = self.I[i] / self.U[i]
            logs[str(i)+'_jacc'] = self.jacc_percl[i]
        self.jacc = np.nanmean(self.jacc_percl)
        logs['jaccard'] = self.jacc

        for i in range(self.n_classes):
            self.val_I[i] = logs['val_I'+str(i)]
            self.val_U[i] = logs['val_U'+str(i)]
            self.val_jacc_percl[i] = self.val_I[i] / self.val_U[i]
            logs[str(i)+'_val_jacc'] = self.val_jacc_percl[i]
        self.val_jacc = np.nanmean(self.val_jacc_percl)
        logs['val_jaccard'] = self.val_jacc



# Save the image results
class Save_results(Callback):
    def __init__(self, n_classes, void_label, save_path,
                 generator, epoch_length, color_map, classes, tag,
                 n_legend_rows=1, *args):
        super(Callback, self).__init__()
        self.n_classes = n_classes
        self.void_label = void_label
        self.save_path = save_path
        self.generator = generator
        self.epoch_length = epoch_length
        self.color_map = color_map
        self.classes = classes
        self.n_legend_rows = n_legend_rows
        self.tag = tag

    def on_epoch_end(self, epoch, logs={}):

        # Create a data generator
        enqueuer = GeneratorEnqueuer(self.generator, wait_time=0.05)
        enqueuer.start(workers=1, max_queue_size=1)

        # Process the dataset
        for _ in range(self.epoch_length):

            # Get data for this minibatch
            data = None
            while enqueuer.is_running():
                if not enqueuer.queue.empty():
                    data = enqueuer.queue.get()
                    break
                else:
                    time.sleep(0.05)
            #data = data_gen_queue.get()
            x_true = data[1][0]
            y_true = data[1][1].astype('int32')

            # Get prediction for this minibatch
            y_pred = self.model.predict(x_true)

            # Reshape y_true and compute the y_pred argmax
            if K.image_dim_ordering() == 'th':
                #Keras API 2.0
               # y_pred = K.resize_images(y_pred, x_true.shape[2], x_true.shape[3], 'channels_first')
                y_pred = np.reshape(y_pred, (y_pred.shape[0], self.model.outputHeight, self.model.outputWidth, x_true.shape[3]))
                y_true = np.reshape(y_true, (y_true.shape[0],y_true.shape[1] ,x_true.shape[2], x_true.shape[3]))
                y_pred = np.argmax(y_pred, axis=1)
                y_true = np.argmax(y_true, axis=1)
            else:
               # y_pred = K.resize_images(y_pred, x_true.shape[1], x_true.shape[2], 'channels_last')
                y_pred = np.reshape(y_pred, (y_true.shape[0], self.model.outputHeight, self.model.outputWidth, y_pred.shape[2]))
                print(y_true.shape)
                y_true = np.reshape(y_true, (y_pred.shape[0], x_true.shape[1], x_true.shape[2], y_true.shape[2]))
                y_pred = np.argmax(y_pred, axis=3)
                y_true = np.argmax(y_true, axis=3)

            # Save output images
            save_img3(x_true, y_true, y_pred, self.save_path, epoch,
                      self.color_map, self.classes, self.tag+str(_), self.void_label,
                      self.n_legend_rows)

        # Stop data generator
        if enqueuer is not None:
            enqueuer.stop()


# Deprecated
class LRDecayScheduler(Callback):
    """
    Decays the learning rate by the specified decay rate (> 1) at specific epochs, or for each epoch
    if decay_epochs is None.
    The updated learning rate is: lr <-- lr / decay_rate
    """
    def __init__(self, decay_epochs, decay_rate):
        super(LRDecayScheduler, self).__init__()
        self.decay_epochs = decay_epochs
        self.decay_rate = decay_rate

    def on_epoch_begin(self, epoch, logs=None):
        current_lr = float(K.get_value(self.model.optimizer.lr))
        try:
            new_lr = current_lr / self.decay_rate
            if (self.decay_epochs is None) or ((epoch+1) in self.decay_epochs):
                # Decay current learning rate and assign it to the model
                K.set_value(self.model.optimizer.lr, new_lr)
                print('    \nLearning rate decayed by a factor of {}: {:.2E} --> {:.2E}\n'.format(
                    self.decay_rate,
                    current_lr,
                    new_lr
                )
                )
        except TypeError:
            raise ValueError('Decay rate for LRDecayScheduler must be a number.\n'
                             'Decay epochs for LRDecayScheduler must be a list of numbers.')


class Scheduler():
    """ Learning rate scheduler function
    # Arguments
        scheduler_type: ['linear' | 'step' | 'square' | 'sqrt']
        lr: initial learning rate
        M: number of learning iterations
        decay: decay coefficient
        S: step iteration
        from: https://arxiv.org/pdf/1606.02228.pdf
        poly from: https://arxiv.org/pdf/1606.00915.pdf
    """
    def __init__(self, scheduler_type='linear', lr=0.001, M=320000,
                 decay=0.1, S=100000, power=0.9):
        # Save parameters
        self.scheduler_type = scheduler_type
        self.lr = float(lr)
        self.decay = float(decay)
        self.M = float(M)
        self.S = S
        self.power = power

        # Get function
        if self.scheduler_type == 'linear':
            self.scheduler_function = self.linear_scheduler
        elif self.scheduler_type == 'step':
            self.scheduler_function = self.step_scheduler
        elif self.scheduler_type == 'square':
            self.scheduler_function = self.square_scheduler
        elif self.scheduler_type == 'sqrt':
            self.scheduler_function = self.sqrt_scheduler
        elif self.scheduler_type == 'poly':
            self.scheduler_function = self.poly_scheduler
        else:
            raise ValueError('Unknown scheduler: ' + self.scheduler_type)

    def step_scheduler(self, i):
        return self.lr * math.pow(self.decay, math.floor(i/self.M))

    def linear_scheduler(self, i):
        return self.lr * (1. - i/self.M)

    def square_scheduler(self, i):
        return self.lr * ((1. - i/self.M)**2)

    def sqrt_scheduler(self, i):
        return self.lr * math.sqrt(1. - i/self.M)

    def poly_scheduler(self, i):
        return self.lr * ((1. - i/self.M)**self.power)


class LearningRateSchedulerBatch(Callback):
    """Learning rate scheduler.

    # Arguments
        schedule: a function that takes an epoch index as input
            (integer, indexed from 0) and returns a new
            learning rate as output (float).
    """

    def __init__(self, schedule):
        super(LearningRateSchedulerBatch, self).__init__()
        self.schedule = schedule
        self.iter = 0

    def on_batch_begin(self, batch, logs=None):
        self.iter += 1
        self.change_lr(self.iter)

    def on_epoch_begin(self, epoch, logs=None):
        lr = self.schedule(self.iter)
        print('   New lr: ' + str(lr))

    def change_lr(self, iteration):
        if not hasattr(self.model.optimizer, 'lr'):
            raise ValueError('Optimizer must have a "lr" attribute.')
        lr = self.schedule(iteration)
        #print('   New lr: ' + str(lr))
        if not isinstance(lr, (float, np.float32, np.float64)):
            raise ValueError('The output of the "schedule" function '
                             'should be float.')
        K.set_value(self.model.optimizer.lr, lr)
