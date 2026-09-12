FROM docker.io/library/node:22-alpine

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

EXPOSE 5173

# Dev server (Phase 1). Phase 5 will add a production build + static serving.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
