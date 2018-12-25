import tensorflow as tf
import data, net
import datetime, pdb

d_pretrain_iter = 0
max_iter = 100000
d_k_step, g_k_step = 15, 3
lr_d, lr_g = 0.0002, 0.0002
show_interval = 50 
batch_size = 64 
noise_size = 100
switch_threshold=1
real_score_threshold=0.95
stddev_scheme = [ii*0.001 for ii in range(10,0,-1)] #[0.01,0.009,...,0.001]
scheme_step = 10
top_k = 5
clip_value = [-0.01,0.01]

tf.reset_default_graph()
image_record = data.readRecord('../data/train.tfrecords')
model_path = '../model/model.ckpt'

## define input
real_image = tf.placeholder(tf.float32, (batch_size,64,64,3))
inptG = tf.placeholder(tf.float32, (batch_size, noise_size))
gn_stddev = tf.placeholder(tf.float32, [])
training = tf.placeholder(tf.bool, [])
fake_image = net.generator(inptG, training)

real_image_batch = data.get_batch_image([image_record], batch_size)
noise_batch = data.get_batch_noise(noise_size, batch_size)
noise_batch_show = data.get_batch_noise(noise_size, top_k)

real_scores = net.discriminator(real_image, gn_stddev, training)
fake_scores = net.discriminator(fake_image, gn_stddev, training)
# topk_scores, topk_index = tf.nn.top_k(tf.reshape(fake_scores,[-1,]),top_k)
m_real_score = tf.reduce_mean(real_scores)
m_fake_score = tf.reduce_mean(fake_scores)

# define losses
d_loss = net.loss_fn_d(real_scores, fake_scores)
g_loss = net.loss_fn_g(fake_scores)

# WGAN-GP gradient penalty
# https://github.com/changwoolee/WGAN-GP-tensorflow/blob/master/model.py
epsilon = tf.random_uniform(
				shape=[batch_size, 1, 1, 1],
				minval=0.,
				maxval=1.)
X_hat = real_image + epsilon * (fake_image - real_image)
D_X_hat = net.discriminator(X_hat, gn_stddev=gn_stddev)
grad_D_X_hat = tf.gradients(D_X_hat, [X_hat])[0]
slopes = tf.sqrt(tf.reduce_sum(tf.square(grad_D_X_hat)))
gradient_penalty = tf.reduce_mean((slopes - 1.) ** 2)
d_loss = d_loss + 10.0 * gradient_penalty

tvars = tf.trainable_variables()
d_vars = [var for var in tvars if 'dis' in var.name]
g_vars = [var for var in tvars if 'gen' in var.name]

print([v.name for v in d_vars])
print([v.name for v in g_vars])
# set trainer to train G and D seperately
update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
with tf.control_dependencies(update_ops):
    d_trainer = tf.train.AdamOptimizer(lr_d).minimize(d_loss, var_list=d_vars)
    # d_trainer = tf.train.RMSPropOptimizer(lr_d).minimize(d_loss, var_list=d_vars)
    g_trainer = tf.train.AdamOptimizer(lr_g).minimize(g_loss, var_list=g_vars)
    # g_trainer = tf.train.RMSPropOptimizer(lr_g).minimize(g_loss, var_list=g_vars)
# clip_d_op = [var.assign(tf.clip_by_value(var, clip_value[0],clip_value[1])) for var in d_vars]

inptG_show = tf.placeholder(tf.float32, (top_k, noise_size))
fake_image_show = net.generator(inptG_show, training)
# add summaries
tf.summary.scalar("Discriminator_loss", d_loss)
tf.summary.scalar("Generator_loss", g_loss)
tf.summary.scalar("Gradient_penalty", gradient_penalty)
tf.summary.image('Generated_images', fake_image_show, top_k)
tf.summary.image('original_images', real_image, top_k)
logdir = "../tensorboard/" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "/"
merged = tf.summary.merge_all()
ginit = tf.global_variables_initializer()
linit = tf.global_variables_initializer()

saver = tf.train.Saver()
with tf.Session() as sess:
    writer = tf.summary.FileWriter(logdir, sess.graph)
    sess.run([ginit, linit])
    coord = tf.train.Coordinator()
    thread = tf.train.start_queue_runners(sess=sess, coord=coord)
    print('start')
    for ii in range(d_pretrain_iter):
        rib = sess.run(real_image_batch)
        finp = sess.run(noise_batch)
        _,dLoss = sess.run([d_trainer,d_loss],
                feed_dict={real_image:rib, inptG:finp})
        if ii % 50 == 0:
            print("dLoss:", dLoss)
            summary = sess.run(merged,{real_image:rib, inptG:finp})
            writer.add_summary(summary,ii)
        #pdb.set_trace()
    train_d = True
    ii = 0
    while True:
        nb_show = sess.run(noise_batch_show) 
        scheme_index = ii//(1000*scheme_step) if ii < 10000*scheme_step else -1
        for jj in range(d_k_step):
            rib = sess.run(real_image_batch)
            nb= sess.run(noise_batch)
            sess.run(d_trainer, feed_dict={real_image:rib, inptG:nb,
                    gn_stddev:stddev_scheme[scheme_index], training:True})
        for kk in range(g_k_step):
            nb= sess.run(noise_batch)
            sess.run(g_trainer, feed_dict={real_image:rib, inptG:nb, 
                    gn_stddev:stddev_scheme[scheme_index], training:True})
        if ii % show_interval == 0:
            real_score,fake_score,dLoss,gLoss = sess.run([m_real_score,m_fake_score,d_loss,g_loss],
                feed_dict={real_image:rib, inptG:nb, gn_stddev:stddev_scheme[scheme_index], training:True})
            print('step ',ii,',dLoss is ',dLoss,',gLoss is ',gLoss,'train_d:',train_d,'real_score and fake score',real_score,fake_score)
            summary = sess.run(merged,{real_image:rib, inptG:nb, inptG_show:nb_show, gn_stddev:0, training:False})
            writer.add_summary(summary,ii)
            saver.save(sess=sess, save_path=model_path)
        ii += 1
    coord.request_stop()
    coord.join(thread)










