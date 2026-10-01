# Self-hosted text detector

txtzi uses `desklib/ai-text-detector-v1.01`, revision
`5fdea974cd4287c61674951ec78803aa274e2fb7`, developed by Desklib.
The publisher declares the model MIT-licensed:
https://huggingface.co/desklib/ai-text-detector-v1.01

Architecture reference: https://github.com/desklib/ai-text-detector
Base architecture: Microsoft's DeBERTa-v3-large.
All credit for original training and weights belongs to the original authors.
txtzi converts the weights to bfloat16, pools in float32, processes overlapping
512-token windows, and reports a token-weighted mean across the full document.
Those deployment choices and the txtzi rewrite workflow are not an endorsement
by Desklib and have not been independently benchmarked for detector accuracy.

## MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
