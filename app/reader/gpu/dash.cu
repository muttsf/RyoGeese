extern "C" __global__ void checksum(const unsigned char* p,int n,unsigned int* out) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;
    if(i<n)for(int c=0;c<4;c++)atomicAdd(out+c,(unsigned int)p[4*i+c]);
}

__device__ int root_of(int* parent,int p) {
    while(parent[p]!=p)p=parent[p];return p;
}
__device__ void join(int* parent,int a,int b) {
    while(true) {a=root_of(parent,a);b=root_of(parent,b);if(a==b)return;
        int hi=a>b?a:b,lo=a<b?a:b;
        if(atomicCAS(parent+hi,hi,lo)==hi)return;
    }
}
extern "C" __global__ void white_init(const unsigned char* p,int n,int* parent,int* stats) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n)return;
    parent[i]=(p[i*4]>=225&&p[i*4+1]>=225&&p[i*4+2]>=225)?i:-1;
    stats[i*5]=2147483647;stats[i*5+1]=2147483647;stats[i*5+2]=-1;stats[i*5+3]=-1;stats[i*5+4]=0;
}
extern "C" __global__ void white_join(int w,int h,int* parent) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=w*h||parent[i]<0)return;
    int x=i%w,y=i/w;
    if(x>0&&parent[i-1]>=0)join(parent,i,i-1);
    if(y>0){
        if(parent[i-w]>=0)join(parent,i,i-w);
        if(x>0&&parent[i-w-1]>=0)join(parent,i,i-w-1);
        if(x+1<w&&parent[i-w+1]>=0)join(parent,i,i-w+1);
    }
}
extern "C" __global__ void white_stats(int w,int h,int* parent,int* stats) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=w*h||parent[i]<0)return;
    int r=root_of(parent,i);int* s=stats+r*5;
    atomicMin(s,i%w);atomicMin(s+1,i/w);atomicMax(s+2,i%w);atomicMax(s+3,i/w);atomicAdd(s+4,1);
}
// Candidate caps are guards, never silent truncation; overflow invalidates this sample.
extern "C" __global__ void marker_candidates(int n,const int* stats,int* counts,double* candidates) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n)return;const int* s=stats+i*5;
    if(s[4]<8)return;int w=s[2]-s[0]+1,h=s[3]-s[1]+1;
    if(w<2||h<2||w>50||h>50)return;double fill=(double)s[4]/(w*h);
    int type=-1,base=0,cap=0;
    if(w>=5&&w<=32&&abs(w-h)<=1&&fill>.95){type=0;base=0;cap=32;}
    else if(abs(w-h)<=2&&fill>.3&&fill<.7){type=1;base=32;cap=128;}
    else if(w>h*2&&fill>.9){type=2;base=160;cap=256;}
    if(type<0)return;int index=atomicAdd(counts+type,1);if(index>=cap)return;
    double* c=candidates+5*(base+index);c[0]=s[0]+(w-1)/2.0;c[1]=s[1]+(h-1)/2.0;c[2]=w;c[3]=h;c[4]=fill;
}
extern "C" __global__ void locate(const int* counts,const double* c,int w,int h,int* results,double* output) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;
    if(counts[0]>32||counts[1]>128||counts[2]>256){if(i==0)results[1]=1;return;}
    if(i>=counts[0]*counts[1])return;
    const double* a=c+5*(i/counts[1]);const double* b=c+5*(32+i%counts[1]);
    double guess=a[2]/8.0,l=a[0]-12*guess,t=a[1]-10*guess;
    if(fabs(b[0]-(l+408*guess))>14||fabs(b[1]-(t+40*guess))>14)return;
    double s0=(b[0]-a[0])/396;if(s0<.5||s0>4)return;
    l=a[0]-12*s0;t=a[1]-10*s0;
    for(int variant=0;variant<2;variant++){
        double bx=variant==0?566:424,ww=variant==0?578:436;
        for(int j=0;j<counts[2];j++){
            const double* d=c+5*(160+j);
            if(fabs(d[0]-(l+bx*s0))>14||fabs(d[1]-(t+292.5*s0))>14)continue;
            for(int k=0;k<counts[2];k++){
                const double* e=c+5*(160+k);
                if(j==k||fabs(e[0]-(l+bx*s0))>14||fabs(e[1]-(t+298.5*s0))>14)continue;
                double xx[4]={12,408,bx,bx},yy[4]={10,40,292.5,298.5};
                double ox[4]={a[0],b[0],d[0],e[0]},oy[4]={a[1],b[1],d[1],e[1]};
                double mx=(12+408+bx+bx)/4,my=(10+40+292.5+298.5)/4;
                double mo=(ox[0]+ox[1]+ox[2]+ox[3])/4,mp=(oy[0]+oy[1]+oy[2]+oy[3])/4;
                double num=0,den=0;
                for(int q=0;q<4;q++){num+=(xx[q]-mx)*(ox[q]-mo)+(yy[q]-my)*(oy[q]-mp);den+=(xx[q]-mx)*(xx[q]-mx)+(yy[q]-my)*(yy[q]-my);}
                double scale=num/den,left=mo-scale*mx,top=mp-scale*my,residual=0;
                for(int q=0;q<4;q++){residual=fmax(residual,fmax(fabs(left+scale*xx[q]-ox[q]),fabs(top+scale*yy[q]-oy[q])));}
                if(residual>2||left<0||top<0||left+ww*scale>w||top+306*scale>h)continue;
                int n=atomicAdd(results,1);if(n>=16){results[1]=1;continue;}
                output[n*5]=scale;output[n*5+1]=left;output[n*5+2]=top;output[n*5+3]=variant;output[n*5+4]=residual;
            }
        }
    }
}
extern "C" __global__ void crop_gpu(const unsigned char* p,int iw,int ih,int x,int y,int w,int h,unsigned char* out) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=w*h*4)return;
    out[i]=p[((y+i/(w*4))*iw+x)*4+i%(w*4)];
}

__device__ bool white_pixel(const unsigned char* p,int w,int x,int y) {
    int q=(y*w+x)*4;return p[q]>=225&&p[q+1]>=225&&p[q+2]>=225;
}
extern "C" __global__ void regions(const unsigned char* p,int iw,int ih,const int* jobs,int n,float* out) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n)return;
    const int* j=jobs+i*6;int kind=j[0],x=j[1],y=j[2],w=j[3],h=j[4];float* r=out+i*4;
    for(int q=0;q<4;q++)r[q]=0;
    if(x<0||y<0||w<=0||h<=0||x+w>iw||y+h>ih){r[0]=-1;return;}
    if(kind==0||kind==4||kind==5){
        int margin=kind==0?1:kind==4?3:2,count=0,total=0;
        for(int yy=y+margin;yy<y+h-margin;yy++)for(int xx=x+margin;xx<x+w-margin;xx++){
            int q=(yy*iw+xx)*4;
            bool yes=kind==0?white_pixel(p,iw,xx,yy):max(p[q],max(p[q+1],p[q+2]))>(kind==4?150:40);
            count+=yes;total++;
        }
        r[0]=kind==4?count:total?(float)count/total:0;return;
    }
    if(kind==1){
        for(int side=0;side<4;side++){
            float best=0;bool hor=side<2;int pos=side==0?y:side==1?y+h:side==2?x:x+w;
            int begin=(hor?x:y)+3,end=(hor?x+w:y+h)-3;
            for(int d=-2;d<=2;d++){
                if(pos+d<0||pos+d>=(hor?ih:iw))continue;int hits=0;
                for(int z=begin;z<end;z++)hits+=white_pixel(p,iw,hor?z:pos+d,hor?pos+d:z);
                best=fmaxf(best,end>begin?(float)hits/(end-begin):0);
            }r[side]=best;
        }return;
    }
    if(kind==2){
        for(int d=-1;d<=2;d++){int hits=0;if(x+d<0||x+d>=iw)continue;
            for(int z=y;z<y+h;z++)hits+=white_pixel(p,iw,x+d,z);r[0]=fmaxf(r[0],(float)hits/h);
        }return;
    }
    if(kind==3){
        int xmin=w,xmax=-1,ymin=h,ymax=-1,count=0;
        for(int yy=j[5];yy<h;yy++)for(int xx=0;xx<w;xx++){
            int q=((yy+y)*iw+xx+x)*4;float b=p[q],g=p[q+1],red=p[q+2];
            if((red>170&&red>1.6*g&&red>1.6*b)||(red>170&&g>140&&b<110)){
                xmin=min(xmin,xx);xmax=max(xmax,xx);ymin=min(ymin,yy);ymax=max(ymax,yy);count++;
            }
        }
        r[0]=count<4?0:(xmax-xmin+1)>1.6*(ymax-ymin+1)?1:(ymax-ymin+1)>1.2*(xmax-xmin+1)?2:3;
        r[1]=count;return;
    }
}
#define BAND 80
#define OUT 160
#define IMG (OUT*OUT*3)
#define META 12
__device__ bool ink(const unsigned char* p) {return max(p[0],max(p[1],p[2]))>150;}
__device__ float cubic_weight(float x) {
    x=fabsf(x);float a=-.75f;
    return x<=1?((a+2)*x-(a+3))*x*x+1:x<2?((a*x-5*a)*x+8*a)*x-4*a:0;
}
// The unchanged x2 cubic operation uses OpenCV's 11-bit separable integer coefficients.
__device__ unsigned char cubic2(const unsigned char* p,int stride,int w,int h,int x,int y,int c) {
    float fx=(x+.5f)*.5f-.5f,fy=(y+.5f)*.5f-.5f;int ix=(int)floorf(fx),iy=(int)floorf(fy);
    long long sum=0;
    for(int a=-1;a<=2;a++)for(int b=-1;b<=2;b++){
        int wx=__float2int_rn(cubic_weight(fx-(ix+b))*2048),wy=__float2int_rn(cubic_weight(fy-(iy+a))*2048);
        sum+=(long long)p[(min(max(iy+a,0),h-1)*stride+min(max(ix+b,0),w-1))*3+c]*wx*wy;
    }
    return (unsigned char)min(255LL,max(0LL,(sum+(1LL<<21))>>22));
}
extern "C" __global__ void prepare_cells(const unsigned char* p,int iw,int ih,const int* jobs,int n,
    unsigned char* bands,int* scratch,unsigned char* images,int* meta) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n)return;
    const int* j=jobs+i*6;int x=j[0]+j[4],y=j[1]+j[4],w=j[2]-2*j[4],h=j[3]-2*j[4];
    if(j[5]>0)h=min(h,j[5]);int* m=meta+i*META;for(int q=0;q<META;q++)m[q]=0;
    unsigned char* b=bands+i*BAND*BAND*3;int* queue=scratch+i*BAND*BAND*2;int* seen=queue+BAND*BAND;
    unsigned char* legacy=images+(i*3)*IMG;unsigned char* clean=legacy+IMG;unsigned char* masked=clean+IMG;
    for(int q=0;q<3*IMG;q++)legacy[q]=0;
    if(w<=0||h<=0||w>BAND||h>BAND||x<0||y<0||x+w>iw||y+h>ih){m[0]=1;m[1]=2;return;}
    int xmin=w,ymin=h,xmax=-1,ymax=-1,count=0;
    for(int yy=0;yy<h;yy++)for(int xx=0;xx<w;xx++){
        int dst=(yy*BAND+xx)*3,src=((yy+y)*iw+x+xx)*4;
        for(int c=0;c<3;c++)b[dst+c]=p[src+c];seen[yy*BAND+xx]=0;
        if(ink(b+dst)){xmin=min(xmin,xx);ymin=min(ymin,yy);xmax=max(xmax,xx);ymax=max(ymax,yy);count++;}
    }
    if(count<2){m[0]=1;return;}
    int lw=(xmax-xmin+1)*2+20,lh=(ymax-ymin+1)*2+20;m[5]=lw;m[6]=lh;
    if(lw>OUT||lh>OUT){m[1]=2;return;}
    for(int yy=10;yy<lh-10;yy++)for(int xx=10;xx<lw-10;xx++)for(int c=0;c<3;c++)
        legacy[(yy*OUT+xx)*3+c]=cubic2(b+(ymin*BAND+xmin)*3,BAND,xmax-xmin+1,ymax-ymin+1,xx-10,yy-10,c);
    int edge=3; // ceil(2*scale) throughout the supported 1.30..1.46 CAL range.
    for(int side=0;side<4;side++){
        bool horizontal=side<2,reverse=side==1||side==3;
        int lines=horizontal?h:w,axis=horizontal?w:h,last=-1;int positions[8],num=0;
        for(int z=0;z<min(edge,lines);z++){
            int actual=reverse?lines-1-z:z,hits=0;
            for(int q=0;q<axis;q++)hits+=ink(b+((horizontal?actual:q)*BAND+(horizontal?q:actual))*3);
            if(hits>=.9*axis){positions[num++]=actual;last=z;}
        }
        if(num==0||last+3>lines)continue;bool blank=true;
        for(int z=last+1;z<last+3;z++)for(int q=0;q<axis;q++){
            int actual=reverse?lines-1-z:z;if(ink(b+((horizontal?actual:q)*BAND+(horizontal?q:actual))*3))blank=false;
        }
        if(!blank)continue;m[2]=1;
        for(int z=0;z<num;z++)for(int q=0;q<axis;q++)for(int c=0;c<3;c++)b[((horizontal?positions[z]:q)*BAND+(horizontal?q:positions[z]))*3+c]=0;
    }
    xmin=w;ymin=h;xmax=-1;ymax=-1;count=0;
    for(int yy=0;yy<h;yy++)for(int xx=0;xx<w;xx++)if(ink(b+(yy*BAND+xx)*3)){
        xmin=min(xmin,xx);ymin=min(ymin,yy);xmax=max(xmax,xx);ymax=max(ymax,yy);count++;
        if(yy==0||xx==0||yy==h-1||xx==w-1)m[4]=1;
        if(seen[yy*BAND+xx])continue;
        int begin=0,end=1;queue[0]=yy*BAND+xx;seen[yy*BAND+xx]=1;
        while(begin<end){int v=queue[begin++],qx=v%BAND,qy=v/BAND;
            for(int dy=-1;dy<=1;dy++)for(int dx=-1;dx<=1;dx++){
                int nx=qx+dx,ny=qy+dy;if(nx<0||ny<0||nx>=w||ny>=h)continue;int idx=ny*BAND+nx;
                if(!seen[idx]&&ink(b+idx*3)){seen[idx]=1;queue[end++]=idx;}
            }
        }if(end>=6)m[3]++;
    }
    if(count<2){m[1]=1;return;}
    int cw=xmax-xmin+11,ch=ymax-ymin+11;m[7]=cw;m[8]=ch;
    for(int yy=5;yy<ch-5;yy++)for(int xx=5;xx<cw-5;xx++)for(int c=0;c<3;c++)clean[(yy*OUT+xx)*3+c]=b[((yy-5+ymin)*BAND+xx-5+xmin)*3+c];
    m[9]=(cw-10)*2+20;m[10]=(ch-10)*2+20;
    // A2 retry: threshold clean native glyph, x2 cubic, pad10; the original pixels stay unchanged.
    for(int yy=ymin;yy<=ymax;yy++)for(int xx=xmin;xx<=xmax;xx++){
        unsigned char v=ink(b+(yy*BAND+xx)*3)?255:0;for(int c=0;c<3;c++)b[(yy*BAND+xx)*3+c]=v;
    }
    for(int yy=10;yy<m[10]-10;yy++)for(int xx=10;xx<m[9]-10;xx++)for(int c=0;c<3;c++)
        masked[(yy*OUT+xx)*3+c]=cubic2(b+(ymin*BAND+xmin)*3,BAND,cw-10,ch-10,xx-10,yy-10,c);
}
extern "C" __global__ void template_scores(const unsigned char* images,const int* meta,int n,
    const unsigned char* refs,const int* specs,int refcount,float* out) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n*refcount)return;int cell=i/refcount,ref=i%refcount;
    const int* m=meta+cell*META;const unsigned char* img=images+cell*3*IMG;
    if(m[0]||m[1]==2){out[i]=0;return;}int xmin=m[5],ymin=m[6],xmax=-1,ymax=-1;
    for(int y=0;y<m[6];y++)for(int x=0;x<m[5];x++)if(ink(img+(y*OUT+x)*3)){
        xmin=min(xmin,x);xmax=max(xmax,x);ymin=min(ymin,y);ymax=max(ymax,y);
    }
    const int* s=specs+ref*3;int rw=s[1],rh=s[2],w=xmax-xmin+1,h=ymax-ymin+1;
    if(w<=0||h<=0||fabs((double)w/h-(double)rw/rh)/((double)rw/rh)>.08){out[i]=0;return;}
    int both=0,either=0;
    for(int y=0;y<rh;y++)for(int x=0;x<rw;x++){
        bool a=ink(img+((ymin+(y*h/rh))*OUT+xmin+(x*w/rw))*3),b=refs[s[0]+y*rw+x]>0;
        both+=a&&b;either+=a||b;
    }out[i]=(float)both/max(1,either);
}
// Equivalent 8-bit OpenCV linear resize followed by BGR CHW normalization.
extern "C" __global__ void normalize(const unsigned char* images,const int* specs,int batch,int width,float* output) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=batch*3*48*width)return;
    int x=i%width,y=(i/width)%48,c=(i/(width*48))%3,b=i/(width*48*3);
    const int* s=specs+b*5;int w=s[2],h=s[3],rw=s[4];
    if(x>=rw){output[i]=0;return;}
    const unsigned char* p=images+(s[0]*3+s[1])*IMG;
    float fx=(x+.5f)*w/rw-.5f,fy=(y+.5f)*h/48-.5f;
    int ix=(int)floorf(fx),iy=(int)floorf(fy);float ax=fx-ix,ay=fy-iy;
    if(ix<0){ix=0;ax=0;}if(ix>=w-1){ix=w-1;ax=0;}
    int wx1=__float2int_rn(ax*2048),wx0=__float2int_rn((1-ax)*2048),wy1=__float2int_rn(ay*2048),wy0=__float2int_rn((1-ay)*2048);
    int y0=min(max(iy,0),h-1),y1=min(max(iy+1,0),h-1),x1=min(ix+1,w-1);
    int a=p[(y0*OUT+ix)*3+c]*wx0+p[(y0*OUT+x1)*3+c]*wx1;
    int b0=p[(y1*OUT+ix)*3+c]*wx0+p[(y1*OUT+x1)*3+c]*wx1;
    int value=(a*wy0+b0*wy1+(1<<21))>>22;
    output[i]=((float)value/255-.5f)/.5f;
}
extern "C" __global__ void ctc(const float* p,int batch,int steps,int chars,int* ids,float* scores,int* lengths) {
    int b=blockIdx.x*blockDim.x+threadIdx.x;if(b>=batch)return;int last=-1,n=0;double sum=0;
    for(int t=0;t<steps;t++){
        const float* row=p+(b*steps+t)*chars;int id=0;float val=row[0];
        for(int c=1;c<chars;c++)if(row[c]>val){val=row[c];id=c;}
        if(id!=0&&id!=last){if(n>=64){lengths[b]=-1;return;}ids[b*64+n++]=id;sum+=round((double)val*100000)/100000;}
        last=id;
    }lengths[b]=n;scores[b]=n?(float)(round(sum/n*100000)/100000):0;
}
