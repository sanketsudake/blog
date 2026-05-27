+++
title = "Posts"

# Each post bundle ships a feature.png — a social-share (OG) card with the title
# baked in, used only for og:image / Twitter cards. Suppress Congo's on-page
# feature-image hero (it would just repeat the title above the article) by
# pointing .Params.feature at a glob that matches no resource. og:image still
# resolves feature.png via Hugo's own "*feature*" lookup, which ignores this param.
[cascade]
  feature = "no-onpage-feature"
+++
