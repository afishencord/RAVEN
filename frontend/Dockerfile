ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api

FROM node:20-alpine AS deps

WORKDIR /app
COPY package.json ./
RUN npm install

FROM node:20-alpine AS builder

ARG NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-alpine AS runner

ENV NODE_ENV=production

WORKDIR /app
COPY --from=builder /app ./

EXPOSE 3000

CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]
