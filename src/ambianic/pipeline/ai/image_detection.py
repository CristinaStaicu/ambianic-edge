"""Tensorflow image detection wrapper."""
import logging
import time
import re
import numpy as np
# from importlib import import_module
from PIL import ImageOps
from .inference import TFInferenceEngine
from ambianic.pipeline import PipeElement


log = logging.getLogger(__name__)


class TFImageDetection(PipeElement):
    """Applies Tensorflow image detection."""

    def __init__(self,
                 model=None,
                 labels=None,
                 confidence_threshold=0.6,
                 top_k=3,
                 **kwargs
                 ):
        """Initialize detector with config parameters.

        :Parameters:
        ----------
        model: ai_models/mobilenet_ssd_v2_face.tflite
        labels: ai_models/coco_labels.txt
        confidence_threshold: 0.6
        top_k: 3

        """
        # log.warning('TFImageDetection __init__ invoked')
        super().__init__(**kwargs)

        self._tfengine = TFInferenceEngine(
            model=model,
            labels=labels,
            confidence_threshold=confidence_threshold,
            top_k=top_k)
        self._labels = self.load_labels(self._tfengine.labels_path)
        self.last_time = time.monotonic()

    def load_labels(self, label_path=None):
        """Load label mapping from integer code to text.

        :Parameters:
        ----------
        label_path : string
            Path to label mapping file.

        :Returns:
        -------
        dict
            {label_code, label_text}

        """
        assert label_path
        p = re.compile(r'\s*(\d+)(.+)')
        with open(label_path, 'r', encoding='utf-8') as f:
            lines = (p.match(line).groups() for line in f.readlines())
            return {int(num): text.strip() for num, text in lines}

    def thumbnail(self, image=None, desired_size=None):
        """Resizes original image as close as possible to desired size.

        Preserves aspect ratio of original image.
        Does not modify the original image.

        :Parameters:
        ----------
        image : PIL.Image
            Input Image for AI model detection.

        desired_size : (width, height)
            Size expected by the AI model.

        :Returns:
        -------
        PIL.Image
            Resized image fitting for the AI model input tensor.

        """
        assert image
        assert desired_size
        log.debug('input image size = %r', image.size)
        thumb = image.copy()
        w, h = desired_size
        try:
            # convert from numpy to native Python int type
            # that PIL expects
            if isinstance(w, np.generic):
                w = w.item()
                w = int(w)
                h = h.item()
                h = int(h)
            thumb.thumbnail((w, h))
        except Exception as e:
            msg = (f"Exception in "
                   f"PIL.image.thumbnail(desired_size={desired_size}):"
                   f"type(width)={type(w)}, type(height)={type(h)}"
                   f"\n{e}"
                   )
            log.exception(msg)
            raise RuntimeError(msg)
        log.debug('thmubnail image size = %r', thumb.size)
        return thumb

    def resize(self, image=None, desired_size=None):
        """Pad original image to exact size expected by input tensor.

        Preserve aspect ratio to avoid confusing the AI model with
        unnatural distortions. Pad the resulting image
        with solid black color pixels to fill the desired size.

        Do not modify the original image.

        :Parameters:
        ----------
        image : PIL.Image
            Input Image sized to fit an input tensor but without padding.
            Its possible that one size fits one tensor dimension exactly
            but the other size is smaller than
            the input tensor other dimension.

        desired_size : (width, height)
            Exact size expected by the AI model.

        :Returns:
        -------
        PIL.Image
            Resized image fitting exactly the AI model input tensor.

        """
        assert image
        assert desired_size
        log.debug('input image size = %r', image.size)
        thumb = image.copy()
        delta_w = desired_size[0] - thumb.size[0]
        delta_h = desired_size[1] - thumb.size[1]
        padding = (0, 0, delta_w, delta_h)
        new_im = ImageOps.expand(thumb, padding)
        log.debug('new image size = %r', new_im.size)
        assert new_im.size == desired_size
        return new_im

    def _log_stats(self, start_time=None):
        assert start_time
        log.debug("TF engine returned inference results")
        end_time = time.monotonic()
        inf_time = (end_time - start_time) * 1000
        fps = 1.0/(end_time - self.last_time)
        if self.context and self.context.unique_pipeline_name:
            pipeline_name = self.context.unique_pipeline_name
        else:
            pipeline_name = 'unknown'
        inf_info = 'Inference time %.2f ms, %.2f fps in pipeline %s'
        log.info(inf_info, inf_time, fps, pipeline_name)
        self.last_time = end_time

    def detect(self, image=None):
        """Detect objects in image.

        :Parameters:
        ----------
        image : PIL.Image
            Input image in raw RGB format
            with the exact size of the input tensor.

        :Returns:
        -------
        list of tuples
            List of top_k detections above confidence_threshold.
            Each detection is a tuple of:
            (label, confidence, (x0, y0, x1, y1))

        """
        assert image
        start_time = time.monotonic()
        log.debug("Calling TF engine for inference")

        tfe = self._tfengine

        # NxHxWxC, H:1, W:2
        height = tfe.input_details[0]['shape'][1]
        width = tfe.input_details[0]['shape'][2]

        # thumbnail is a proportionately resized image
        thumbnail = self.thumbnail(image=image, desired_size=(width, height))

        # convert thumbnail into an image with the exact size
        # as the input tensor
        # preserving proportions by padding as needed
        new_im = self.resize(image=thumbnail, desired_size=(width, height))

        # calculate what fraction of the new image is the thumbnail size
        # we will use these factors to adjust detection box coordinates
        w_factor = thumbnail.size[0] / new_im.size[0]
        h_factor = thumbnail.size[1] / new_im.size[1]

        # add N dim
        input_data = np.expand_dims(new_im, axis=0)
        # log.warning('input_data.shape: %r', input_data.shape)
        # log.warning('input_data.dtype: %r', input_data.dtype)
        # input_data = input_data.astype(np.uint8)
        # log.warning('input_data.dtype: %r', input_data.dtype)
        # input_data = np.asarray(input_data).flatten()

        # Note: Floating models are not tested thoroughly yet.
        # Its not clear yet whether floating models will be a good fit
        # for Ambianic use cases. Optimized quantized models seem to do
        # a good job in terms of accuracy and speed.
        if not tfe.is_quantized:  # pragma: no cover
            # normalize floating point values
            input_mean = 127.5
            input_std = 127.5
            input_data = \
                (np.float32(input_data) - input_mean) / input_std

        tfe.set_tensor(tfe.input_details[0]['index'], input_data)

        # invoke inference on the new input data
        # with the configured model
        tfe.infer()

        self._log_stats(start_time=start_time)

        # log.debug('output_details: %r', tfe.output_details)
        # od = tfe.output_details[0]['index']
        # log.debug('output_data[0]: %r',
        #             tfe.get_tensor(od))
        # log.debug('output_data[0]: %r',
        #             tfe._tf_interpreter.get_tensor(od))

        # get output tensor
        boxes = tfe.get_tensor(tfe.output_details[0]['index'])
        label_codes = tfe.get_tensor(
            tfe.output_details[1]['index'])
        scores = tfe.get_tensor(tfe.output_details[2]['index'])
        num = tfe.get_tensor(tfe.output_details[3]['index'])
        # log.warning('Detections:\n num: %r\n label_codes: %r\n scores: %r\n',
        #             num, label_codes, scores)
        # log.warning('Required confidence: %r',
        #             tfe.confidence_threshold)
        detections_count = int(num[0])

        inference_result = []
        # get a list of indices for the top_k results
        # ordered from highest to lowest confidence.
        # We are only interested in scores within detections_count range
        indices_of_sorted_scores = np.argsort(scores[0, :detections_count])
        # log.warning('Indices of sorted scores: %r:',
        #             indices_of_sorted_scores)
        top_k_indices = indices_of_sorted_scores[-1*tfe.top_k:][::-1]
        # log.warning('Indices of top_k scores: %r:', top_k_indices)
        # from the top_k results, only take the ones that score
        # above the confidence threshold criteria.
        for i in top_k_indices:
            confidence = scores[0, i]
            if confidence >= tfe.confidence_threshold:
                # log.warning('Sample confidence: %r, required confidence %r',
                #             confidence, tfe.confidence_threshold)
                li = int(label_codes[0, i])
                # protect against models that return arbitrary labels
                # when the confidence is low
                if (li < len(self._labels)):
                    label = self._labels[li]
                    box = boxes[0, i, :]
                    # refit detections into original image size
                    # without overflowing outside image borders
                    x0 = box[1] / w_factor
                    y0 = box[0] / h_factor
                    x1 = min(box[3] / w_factor, 1)
                    y1 = min(box[2] / h_factor, 1)
                    log.debug('thumbnail image size: %r , '
                              'tensor image size: %r',
                              thumbnail.size,
                              new_im.size)
                    log.debug('resizing detection box (x0, y0, x1, y1) '
                              'from: %r to %r',
                              (box[1], box[0], box[3], box[2]),
                              (x0, y0, x1, y1))
                    inference_result.append((
                        label,
                        confidence,
                        (x0, y0, x1, y1)))
        return thumbnail, new_im, inference_result
